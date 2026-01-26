# src/neo4j_driver.py
from typing import Optional, List, Dict, Any
from datetime import datetime
from neo4j import GraphDatabase, Record
from commit_details import CommitDetails
import config
import time
import json
import logging
from git import Commit, Actor, Repo, TagReference

logger = logging.getLogger(__name__)


class Neo4jDriver:
    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        max_retries: int = 5,
        retry_delay: int = 2,
    ):
        self._uri = uri or config.NEO4J_URI
        self._auth = (user or config.APP_NEO4J_USER, password or config.APP_NEO4J_PASSWORD)
        for attempt in range(max_retries):
            try:
                self.driver = GraphDatabase.driver(
                    self._uri,
                    auth=self._auth
                )
                self.driver.verify_connectivity()  # Ensure connection works
                logger.info("Connected to Neo4j successfully.")
                break
            except Exception as e:
                logger.error(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    raise Exception("Failed to connect to Neo4j after retries.")

    def close(self):
        if self.driver:
            self.driver.close()

    @property
    def _driver(self):
        """Property that ensures the driver is initialized before use."""
        assert self.driver is not None, "Neo4j driver has not been initialized"
        return self.driver

    @staticmethod
    def _require_single_record(result, error_message: str):
        """Helper to extract a single record from a query result, raising an error if None."""
        record = result.single()
        if record is None:
            raise RuntimeError(error_message)
        return record

    def clear_database(self):
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            logger.info("Database cleared.")

    def create_node(self, label, properties):
        with self.driver.session() as session:
            # Validate label to prevent injection (alphanumeric and underscores only)
            if not label.replace("_", "").isalnum():
                raise ValueError(f"Invalid label: {label}. Labels must contain only alphanumeric characters and underscores.")
            query = f"MERGE (n:{label} $props) RETURN n"
            result = session.run(query, props=properties)  # type: ignore[arg-type]
            record = self._require_single_record(result, f"Failed to create or retrieve node with label {label}")
            return record["n"]
    
    @staticmethod
    def tx_insert_actor(tx, actor) -> str:
        result = tx.run("""
            MERGE (a: Actor {name: $name, email: $email})
            RETURN a.email as email
            """,
            name=actor.name,
            email=actor.email
        )
        record = Neo4jDriver._require_single_record(result, f"Failed to create or retrieve actor {actor.name}")
        return record["email"]

    def merge_actor(self, actor: Actor) -> str:
        with self.driver.session() as session:
            query = """
            MERGE (a:Actor {name: $name, email: $email})
            RETURN id(a) AS node_id
            """
            result = session.run(query, name=actor.name, email=actor.email)
            record = self._require_single_record(result, "Failed to create or retrieve node with label Actor")
            return str(record["node_id"])

    def merge_actor_node(self, properties) -> Record:
        with self.driver.session() as session:
            query = "MERGE (n:Actor {name: $props.name, email: $props.email}) RETURN n"
            result = session.run(query, props=properties)
            logger.debug(f"merge actor ${properties.name}")
            record = self._require_single_record(result, "Failed to create or retrieve node with label Actor")
            return record["n"]
        
    def add_commit(self, author_props, commit_props):
        # breakpoint()
        self.driver.execute_query(
            "MERGE (a:Actor {name: $author.name, email: $author.email}) "
            "MERGE (c:Commit {hexsha: $commit.hexsha}) "
            "MERGE (a)-[:AUTHORED]->(c) "
            "return a.email as email",
            author=author_props, commit=commit_props
        )

    def get_all_actors(self):
        with self.driver.session() as session:
            query = "MATCH (a:Actor) RETURN a.name AS name, a.email AS email"
            result = session.run(query)
            return [record.data() for record in result]

    def get_all_identities(self):
        """Get all Identity nodes (replaces get_all_actors)."""
        with self.driver.session() as session:
            query = "MATCH (i:Identity) RETURN i.name AS name, i.email AS email, i.source AS source"
            result = session.run(query)
            return [record.data() for record in result]

    def get_all_identity_emails(self, limit: Optional[int] = None) -> List[str]:
        """Get all identity emails from Identity nodes."""
        with self.driver.session() as session:
            query = """
            MATCH (i:Identity)
            WHERE i.source = 'git'
            RETURN DISTINCT i.email as email
            ORDER BY i.email
            """
            if limit:
                query += f" LIMIT {limit}"
            result = session.run(query)
            emails = [record["email"] for record in result]
            return emails

    def get_actor_with_commits(self, email: str):
        with self.driver.session() as session:
            query = """
                MATCH (a:Actor {email: $email})
                OPTIONAL MATCH (a)-[:AUTHORED]->(authored:Commit)
                OPTIONAL MATCH (a)-[:COMMITTED]->(committed:Commit)
                RETURN 
                    a.name AS name,
                    a.email AS email,
                    collect(DISTINCT {commit_hash: authored.commit_hash, message: authored.message}) AS authored_commits,
                    collect(DISTINCT {commit_hash: committed.commit_hash, message: committed.message}) AS committed_commits
            """
            result = session.run(query, email=email)
            record = result.single()
            if not record:
                return None
            return {
                "name": record["name"],
                "email": record["email"],
                "authored_commits": record["authored_commits"],
                "committed_commits": record["committed_commits"]
            }

    def get_identity_with_commits(self, email: str, source: str = "git"):
        """Get identity with commits (replaces get_actor_with_commits)."""
        with self.driver.session() as session:
            query = """
                MATCH (i:Identity {email: $email, source: $source})
                OPTIONAL MATCH (i)-[:AUTHORED]->(authored:Commit)
                OPTIONAL MATCH (i)-[:COMMITTED]->(committed:Commit)
                RETURN 
                    i.name AS name,
                    i.email AS email,
                    i.source AS source,
                    collect(DISTINCT {commit_hash: authored.commit_hash, message: authored.message}) AS authored_commits,
                    collect(DISTINCT {commit_hash: committed.commit_hash, message: committed.message}) AS committed_commits
            """
            result = session.run(query, email=email, source=source)
            record = result.single()
            if not record:
                return None
            return {
                "name": record["name"],
                "email": record["email"],
                "source": record.get("source", "git"),
                "authored_commits": record["authored_commits"],
                "committed_commits": record["committed_commits"]
            }


    def get_mismatched_authors_committers(self):
        with self.driver.session() as session:
            query = """
            MATCH (c:Commit)
            MATCH (c)<-[rel_c:COMMITTED]-(committer:Actor) 
            MATCH (c)<-[rel_a:AUTHORED]-(author:Actor) 
            WHERE committer.email <> author.email
            AND rel_c.committed_date > 1542067894
            RETURN 
                c.commit_hash AS commit_hex, 
                author.email AS author_email, 
                committer.email AS committer_email, 
                c AS commit, 
                rel_c.committed_date AS committed_date, 
                rel_a.authored_date AS authored_date 
            LIMIT 10
            """
            result = session.run(query)
            return [
                {
                    "commit_hex": r["commit_hex"],
                    "author_email": r["author_email"],
                    "committer_email": r["committer_email"],
                    "commit": r["commit"],
                    "committed_date": r["committed_date"],
                    "authored_date": r["authored_date"]
                }
                for r in result
                ]

    def merge_github_organization(self, name: str, slug: str):
        with self.driver.session() as session:
            result = session.run(
                """
                MERGE (o:GithubOrganization {slug: $slug})
                ON CREATE SET o.name = $name
                RETURN o
                """,
                slug=slug,
                name=name
            )
            record = self._require_single_record(result, "Failed to create or retrieve node with label GithubOrganization")
            return record["o"]

    def merge_github_repository(self, org_slug: str, name: str, url: str, description: str = ""):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (org:GithubOrganization {slug: $org_slug})
                MERGE (r:GithubRepository {url: $url})
                ON CREATE SET r.name = $name, r.description = $description
                MERGE (org)-[:HAS_REPOSITORY]->(r)
                RETURN r
                """,
                org_slug=org_slug,
                name=name,
                url=url,
                description=description
            )
            record = self._require_single_record(result, "Failed to create or retrieve node with label GithubRepository")
            return record["r"]

    def get_all_github_repositories(self):
        with self.driver.session() as session:
            # Check if GithubRepository label exists first to avoid warnings
            label_check = session.run("CALL db.labels() YIELD label RETURN label")
            labels = [record["label"] for record in label_check]
            if "GithubRepository" not in labels:
                return []
            
            result = session.run(
                """
                MATCH (r:GithubRepository)
                RETURN r.name AS name, r.url AS url, COALESCE(r.description, "") AS description
                """
            )
            return [record.data() for record in result]

    def get_all_github_organizations(self):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (o:GithubOrganization)
                RETURN o.name AS name, o.slug AS slug
                """
            )
            return [record.data() for record in result]

    def get_github_organization_by_slug(self, slug: str):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (o:GithubOrganization {slug: $slug})
                RETURN o.name AS name, o.slug AS slug
                """,
                slug=slug
            )
            return result.single()


    def get_github_repository_by_url(self, url: str):
        with self.driver.session() as session:
            # Check if GithubRepository label exists first to avoid warnings
            label_check = session.run("CALL db.labels() YIELD label RETURN label")
            labels = [record["label"] for record in label_check]
            if "GithubRepository" not in labels:
                return None
            
            result = session.run(
                """
                MATCH (r:GithubRepository)
                WHERE r.url = $url
                RETURN r.name AS name, r.url AS url, COALESCE(r.description, "") AS description
                LIMIT 1
                """,
                url=url
            )
            return result.single()

    # Used for figuring out what import data import steps steps have been completed
    # def get_processing_flags(self):
    #     with self.driver.session() as session:
    #         session.run("MATCH (n:ProcessingEvent)-[e:EXECUTED]->(r:DataSource)")
    
    def insert_folder_level_details(self, data):
        with self.driver.session() as session:
            result = session.execute_write(self._insert_folder_level_details, data)
            return result


    @staticmethod
    def _insert_folder_level_details(tx, data):
        query = """
        MERGE (file_detail_record:FileDetailRecord {master_sha_at_collection: $master_sha_at_collection, file_path: $file_path})
        ON CREATE SET file_detail_record.json_blob = $json_blob
        RETURN file_detail_record
        """
        json_blob = json.dumps(data)
        result = tx.run(query, master_sha_at_collection=data['master_sha_at_collection'], file_path=data['file_paths'], json_blob=json_blob)
        record = result.single()
        return record["file_detail_record"]
    
    def merge_import_status(self):
        with self._driver.session() as session:
            result = session.execute_write(self._merge_import_status_node)
            return result

    @staticmethod
    def _merge_import_status_node(tx):
        query = """
        MERGE (a:ImportStatus)
        ON CREATE SET a.git_import_complete = false, a.next_complete = false
        RETURN a.git_import_complete, a.next_complete
        """
        result = tx.run(query)
        record = result.single()
        if record:
            return {
                "git_import_complete": record["a.git_import_complete"],
                "next_complete": record["a.next_complete"]
            }
        else:
            return {
                "git_import_complete": False,
                "next_complete": False
            }

    def merge_commit_step(self, commit: Commit, committer_node: str, author_node: str, co_author_nodes: list[str]):
        # print('commit merge processing')
        commit_details = CommitDetails(commit)
        # Use id() for Neo4j 4.x compatibility (elementId() is Neo4j 5.x only)
        self._driver.execute_query(
            "match (committer:Actor), (author:Actor)"
            "where id(author) = $author_id "
            "and id(committer) = $committer_id "
            "MERGE (c:Commit {commit_hash: $commit_hash}) "
            "ON CREATE SET c.parent_shas = $parent_shas, "
            " c.message = $message, "
            " c.summary = $summary "
            "MERGE (committer)-[cr:COMMITTED]->(c) "
            "ON CREATE SET cr.committed_date = $committed_date "
            "MERGE (author)-[ca:AUTHORED]->(c) "
            "ON CREATE SET ca.authored_date = $authored_date "
            , committer_id=int(committer_node),
              author_id=int(author_node),
              commit_hash=commit_details.commit_hash,
              parent_shas=commit_details.parent_shas,
              authored_date=commit_details.authored_date,
              committed_date=commit_details.committed_date,
              message=commit_details.message,
              summary=commit_details.summary,
              )

    def merge_get_import_status_node(self):
        with self._driver.session() as session:
            result = session.execute_write(self._create_and_return_import_status_node)
            return result

    @staticmethod
    def _create_and_return_import_status_node(tx):
        query = """
        MERGE (a:ImportStatus)
        ON CREATE SET 
          a.next_complete = false
        SET a.git_import_complete = true
        RETURN a.git_import_complete, a.next_complete
        """
        result = tx.run(query)
        record = result.single()
        return {
            "git_import_complete": record["a.git_import_complete"],
            "next_complete": record["a.next_complete"]
        }

    # ========== New Schema Methods ==========

    def check_and_cleanup_filechange_duplicates(self, cleanup: bool = False) -> Dict[str, Any]:
        """
        Check for duplicate FileChange nodes (same commit_hash and path).
        
        Args:
            cleanup: If True, remove duplicates keeping the first one. If False, only report.
        
        Returns:
            Dict with 'duplicate_count' and 'duplicate_groups' information
        """
        with self._driver.session() as session:
            # Find duplicates
            check_query = """
            MATCH (fc:FileChange)
            WITH fc.commit_hash AS commit_hash, fc.path AS path, collect(fc) AS nodes
            WHERE size(nodes) > 1
            RETURN commit_hash, path, size(nodes) AS count, [n IN nodes | id(n)] AS node_ids
            ORDER BY count DESC
            """
            
            result = session.run(check_query)
            duplicates = []
            total_duplicate_nodes = 0
            
            for record in result:
                commit_hash = record["commit_hash"]
                path = record["path"]
                count = record["count"]
                node_ids = record["node_ids"]
                
                duplicates.append({
                    "commit_hash": commit_hash,
                    "path": path,
                    "count": count,
                    "node_ids": node_ids
                })
                total_duplicate_nodes += (count - 1)  # -1 because we keep one
            
            if duplicates:
                logger.warning(f"Found {len(duplicates)} duplicate FileChange groups affecting {total_duplicate_nodes} nodes")
                
                if cleanup:
                    # Delete duplicates, keeping the first node in each group
                    cleanup_query = """
                    MATCH (fc:FileChange)
                    WITH fc.commit_hash AS commit_hash, fc.path AS path, collect(fc) AS nodes
                    WHERE size(nodes) > 1
                    WITH commit_hash, path, nodes[0] AS keep, nodes[1..] AS to_delete
                    UNWIND to_delete AS duplicate
                    DETACH DELETE duplicate
                    RETURN count(duplicate) AS deleted_count
                    """
                    
                    cleanup_result = session.run(cleanup_query)
                    deleted_record = cleanup_result.single()
                    deleted_count = deleted_record["deleted_count"] if deleted_record else 0
                    logger.info(f"Cleaned up {deleted_count} duplicate FileChange nodes")
                    
                    return {
                        "duplicate_groups": len(duplicates),
                        "duplicate_nodes": total_duplicate_nodes,
                        "deleted_count": deleted_count,
                        "details": duplicates
                    }
                else:
                    # Just report
                    for dup in duplicates[:5]:  # Show first 5
                        logger.warning(f"  Duplicate: commit={dup['commit_hash'][:8]} path={dup['path']} count={dup['count']}")
                    if len(duplicates) > 5:
                        logger.warning(f"  ... and {len(duplicates) - 5} more groups")
                    
                    return {
                        "duplicate_groups": len(duplicates),
                        "duplicate_nodes": total_duplicate_nodes,
                        "deleted_count": 0,
                        "details": duplicates
                    }
            else:
                logger.info("No duplicate FileChange nodes found")
                return {
                    "duplicate_groups": 0,
                    "duplicate_nodes": 0,
                    "deleted_count": 0,
                    "details": []
                }

    def create_constraints(self):
        """Create all required constraints for the new schema."""
        # Check for and clean up FileChange duplicates before creating the constraint
        logger.info("Checking for duplicate FileChange nodes...")
        duplicate_info = self.check_and_cleanup_filechange_duplicates(cleanup=True)
        if duplicate_info["duplicate_groups"] > 0:
            logger.info(f"Cleaned up {duplicate_info['deleted_count']} duplicate FileChange nodes before applying constraint")
        
        with self._driver.session() as session:
            constraints = [
                # Commits
                "CREATE CONSTRAINT commit_hash_unique IF NOT EXISTS FOR (c:Commit) REQUIRE c.commit_hash IS UNIQUE",
                # Identities
                "CREATE CONSTRAINT identity_unique IF NOT EXISTS FOR (i:Identity) REQUIRE (i.source, i.email, i.name) IS UNIQUE",
                # Paths
                "CREATE CONSTRAINT path_unique IF NOT EXISTS FOR (p:Path) REQUIRE p.path IS UNIQUE",
                # Refs - remote must always be set (use empty string if null)
                "CREATE CONSTRAINT ref_unique IF NOT EXISTS FOR (r:Ref) REQUIRE (r.kind, r.name, r.remote) IS UNIQUE",
                # PGP Keys
                "CREATE CONSTRAINT pgpkey_unique IF NOT EXISTS FOR (k:PGPKey) REQUIRE k.fingerprint IS UNIQUE",
                # Ingest Runs
                "CREATE CONSTRAINT ingestrun_unique IF NOT EXISTS FOR (ir:IngestRun) REQUIRE ir.id IS UNIQUE",
                # FileChanges - ensure uniqueness per commit+path
                "CREATE CONSTRAINT filechange_unique IF NOT EXISTS FOR (fc:FileChange) REQUIRE (fc.commit_hash, fc.path) IS UNIQUE",
            ]
            
            for constraint_query in constraints:
                try:
                    session.run(constraint_query)
                    logger.info(f"Created constraint: {constraint_query[:50]}...")
                except Exception as e:
                    logger.error(f"Constraint may already exist or error: {e}")
            
            # Indexes
            indexes = [
                "CREATE INDEX commit_times IF NOT EXISTS FOR (c:Commit) ON (c.committedAt)",
                "CREATE INDEX commit_authored_times IF NOT EXISTS FOR (c:Commit) ON (c.authoredAt)",
                "CREATE INDEX event_times IF NOT EXISTS FOR (e:Event) ON (e.ts)",
            ]
            
            for index_query in indexes:
                try:
                    session.run(index_query)
                    logger.info(f"Created index: {index_query[:50]}...")
                except Exception as e:
                    logger.error(f"Index may already exist or error: {e}")

    def batch_upsert_commits(self, commit_rows: List[Dict[str, Any]], batch_size: int = 1000):
        """
        Batch upsert commits with identities and parent relationships.
        
        Args:
            commit_rows: List of dicts with keys: sha, message, summary, authoredAt, committedAt,
                        isMerge, parents (list of shas), author (dict with source/name/email),
                        committer (dict with source/name/email), coauthors (list of dicts)
            batch_size: Number of commits to process per transaction
        """
        for i in range(0, len(commit_rows), batch_size):
            batch = commit_rows[i:i + batch_size]
            with self._driver.session() as session:
                session.execute_write(self._batch_upsert_commits_tx, batch)
            logger.info(f"Processed commit batch {i//batch_size + 1}/{(len(commit_rows)-1)//batch_size + 1}")

    @staticmethod
    def _batch_upsert_commits_tx(tx, rows: List[Dict[str, Any]]):
        """Transaction function for batch commit upsert."""
        query = """
        UNWIND $rows AS row

        MERGE (c:Commit {commit_hash: row.sha})
        ON CREATE SET
          c.message = row.message,
          c.summary = row.summary,
          c.authoredAt = row.authoredAt,
          c.committedAt = row.committedAt,
          c.isMerge = row.isMerge
        ON MATCH SET
          c.message = row.message,
          c.summary = row.summary,
          c.authoredAt = row.authoredAt,
          c.committedAt = row.committedAt,
          c.isMerge = row.isMerge

        // Author
        MERGE (a:Identity {source: row.author.source, name: row.author.name, email: row.author.email})
        MERGE (a)-[ra:AUTHORED]->(c)
        ON CREATE SET ra.at = row.authoredAt
        ON MATCH SET ra.at = row.authoredAt

        // Committer
        MERGE (m:Identity {source: row.committer.source, name: row.committer.name, email: row.committer.email})
        MERGE (m)-[rm:COMMITTED]->(c)
        ON CREATE SET rm.at = row.committedAt
        ON MATCH SET rm.at = row.committedAt

        // Co-authors (optional)
        FOREACH (co IN coalesce(row.coauthors, []) |
          MERGE (ci:Identity {source: co.source, name: co.name, email: co.email})
          MERGE (ci)-[:CO_AUTHORED]->(c)
        )

        // Parents
        FOREACH (idx IN range(0, size(coalesce(row.parents, [])) - 1) |
          MERGE (p:Commit {commit_hash: row.parents[idx]})
          MERGE (c)-[hp:HAS_PARENT {idx: idx}]->(p)
        )
        """
        tx.run(query, rows=rows)

    def batch_upsert_file_changes(self, change_rows: List[Dict[str, Any]], batch_size: int = 1000):
        """
        Batch upsert file changes for commits.
        
        Args:
            change_rows: List of dicts with keys: sha, changes (list of dicts with path, status, add, del, rename_from, isSensitive)
            batch_size: Number of commits to process per transaction
        """
        for i in range(0, len(change_rows), batch_size):
            batch = change_rows[i:i + batch_size]
            with self._driver.session() as session:
                session.execute_write(self._batch_upsert_file_changes_tx, batch)
            logger.info(f"Processed file change batch {i//batch_size + 1}/{(len(change_rows)-1)//batch_size + 1}")

    @staticmethod
    def _batch_upsert_file_changes_tx(tx, rows: List[Dict[str, Any]]):
        """Transaction function for batch file change upsert."""
        query = """
        UNWIND $rows AS row
        MATCH (c:Commit {commit_hash: row.sha})

        UNWIND row.changes AS ch
        MERGE (p:Path {path: ch.path})
        MERGE (fc:FileChange {commit_hash: row.sha, path: ch.path})
        ON CREATE SET
          fc.status = ch.status,
          fc.add = ch.add,
          fc.del = ch.del,
          fc.rename_from = ch.rename_from,
          fc.isSensitive = ch.isSensitive
        ON MATCH SET
          fc.status = ch.status,
          fc.add = ch.add,
          fc.del = ch.del,
          fc.rename_from = ch.rename_from,
          fc.isSensitive = ch.isSensitive

        MERGE (c)-[:HAS_CHANGE]->(fc)
        MERGE (fc)-[:OF_PATH]->(p)
        """
        tx.run(query, rows=rows)

    def create_ingest_run(self, run_id: str, pulled_at: datetime) -> str:
        """Create an IngestRun node."""
        with self._driver.session() as session:
            result = session.run(
                """
                MERGE (ir:IngestRun {id: $run_id})
                SET ir.pulledAt = $pulled_at,
                    ir.status = 'STARTED',
                    ir.totalCommitsProcessed = 0,
                    ir.totalSignaturesProcessed = 0,
                    ir.totalMergesProcessed = 0,
                    ir.currentStage = 'STARTED',
                    ir.stageStartedAt = $pulled_at,
                    ir.lastProgressAt = $pulled_at
                RETURN ir.id AS id
                """,
                run_id=run_id,
                pulled_at=pulled_at
            )
            record = result.single()
            return record["id"] if record else run_id

    def update_ingest_run_status(self, run_id: str, status: str, **kwargs):
        """Update the status and progress of an IngestRun."""
        from datetime import datetime
        
        with self._driver.session() as session:
            set_clauses = ["ir.status = $status"]
            params = {"run_id": run_id, "status": status}
            
            # Always update lastProgressAt when status changes
            now = datetime.now()
            set_clauses.append("ir.lastProgressAt = $now")
            params["now"] = now
            
            # If status is changing, update currentStage and stageStartedAt
            if "currentStage" not in kwargs:
                set_clauses.append("ir.currentStage = $status")
                set_clauses.append("ir.stageStartedAt = $now")
            
            for key, value in kwargs.items():
                if value is not None:
                    set_clauses.append(f"ir.{key} = ${key}")
                    params[key] = value
            
            query = f"""
            MATCH (ir:IngestRun {{id: $run_id}})
            SET {', '.join(set_clauses)}
            """
            
            session.run(query, **params)
            logger.info(f"Updated IngestRun {run_id} status to {status} {kwargs if kwargs else ''}")

    def get_ingest_run_status(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the status and progress of an IngestRun."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (ir:IngestRun {id: $run_id})
                RETURN ir.id AS id, ir.status AS status, ir.pulledAt AS pulledAt, 
                       ir.totalCommitsProcessed AS totalCommitsProcessed,
                       ir.totalSignaturesProcessed AS totalSignaturesProcessed,
                       ir.totalMergesProcessed AS totalMergesProcessed,
                       ir.currentStage AS currentStage,
                       ir.stageStartedAt AS stageStartedAt,
                       ir.lastProgressAt AS lastProgressAt
                """,
                run_id=run_id
            )
            record = result.single()
            if record:
                return {
                    "id": record["id"],
                    "status": record["status"],
                    "pulledAt": record["pulledAt"],
                    "totalCommitsProcessed": record.get("totalCommitsProcessed", 0),
                    "totalSignaturesProcessed": record.get("totalSignaturesProcessed", 0),
                    "totalMergesProcessed": record.get("totalMergesProcessed", 0),
                    "currentStage": record.get("currentStage"),
                    "stageStartedAt": record.get("stageStartedAt"),
                    "lastProgressAt": record.get("lastProgressAt")
                }
            return None
    
    def get_active_ingest_runs(self) -> List[Dict[str, Any]]:
        """Get all active (non-completed) ingest runs."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (ir:IngestRun)
                WHERE ir.status <> 'COMPLETED'
                RETURN ir.id AS id, ir.status AS status, ir.pulledAt AS pulledAt,
                       ir.totalCommitsProcessed AS totalCommitsProcessed,
                       ir.totalSignaturesProcessed AS totalSignaturesProcessed,
                       ir.totalMergesProcessed AS totalMergesProcessed
                ORDER BY ir.pulledAt DESC
                """
            )
            runs = []
            for record in result:
                runs.append({
                    "id": record["id"],
                    "status": record["status"],
                    "pulledAt": record["pulledAt"],
                    "totalCommitsProcessed": record.get("totalCommitsProcessed", 0),
                    "totalSignaturesProcessed": record.get("totalSignaturesProcessed", 0),
                    "totalMergesProcessed": record.get("totalMergesProcessed", 0)
                })
            return runs
    
    def get_recent_ingest_runs(self, limit: int = 3) -> List[Dict[str, Any]]:
        """Get the most recent ingest runs (all statuses)."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (ir:IngestRun)
                RETURN ir.id AS id, ir.status AS status, ir.pulledAt AS pulledAt,
                       ir.totalCommitsProcessed AS totalCommitsProcessed,
                       ir.totalSignaturesProcessed AS totalSignaturesProcessed,
                       ir.totalMergesProcessed AS totalMergesProcessed
                ORDER BY ir.pulledAt DESC
                LIMIT $limit
                """,
                limit=limit
            )
            runs = []
            for record in result:
                runs.append({
                    "id": record["id"],
                    "status": record["status"],
                    "pulledAt": record["pulledAt"],
                    "totalCommitsProcessed": record.get("totalCommitsProcessed", 0),
                    "totalSignaturesProcessed": record.get("totalSignaturesProcessed", 0),
                    "totalMergesProcessed": record.get("totalMergesProcessed", 0)
                })
            return runs

    def snapshot_refs(self, run_id: str, refs: List[Dict[str, Any]]):
        """
        Create RefState snapshots for an IngestRun.
        
        Args:
            run_id: IngestRun ID
            refs: List of dicts with keys: name, kind, remote (optional), tipSha
        """
        with self._driver.session() as session:
            session.execute_write(self._snapshot_refs_tx, run_id, refs)

    @staticmethod
    def _snapshot_refs_tx(tx, run_id: str, refs: List[Dict[str, Any]]):
        """Transaction function for ref snapshotting."""
        # Ensure remote is always a string (empty if None) before query
        for ref_data in refs:
            if ref_data.get('remote') is None:
                ref_data['remote'] = ''
        
        query = """
        MATCH (ir:IngestRun {id: $run_id})
        UNWIND $refs AS ref_data

        MERGE (r:Ref {kind: ref_data.kind, name: ref_data.name, remote: ref_data.remote})
        MERGE (tip:Commit {commit_hash: ref_data.tipSha})
        MERGE (rs:RefState {name: ref_data.name, kind: ref_data.kind, remote: ref_data.remote, tipSha: ref_data.tipSha})
        MERGE (ir)-[:SAW_REF]->(rs)
        MERGE (rs)-[:POINTS_TO]->(tip)
        MERGE (r)-[:POINTS_TO]->(tip)
        """
        tx.run(query, run_id=run_id, refs=refs)

    def upsert_tags(self, tags: List[Dict[str, Any]]):
        """
        Upsert tag objects.
        
        Args:
            tags: List of dicts with keys: name, taggerAt, message, targetSha, tagger (dict with source/name/email)
        """
        with self._driver.session() as session:
            session.execute_write(self._upsert_tags_tx, tags)

    @staticmethod
    def _upsert_tags_tx(tx, tags: List[Dict[str, Any]]):
        """Transaction function for tag upsert."""
        query = """
        UNWIND $tags AS tag_data

        MERGE (to:TagObject {name: tag_data.name})
        ON CREATE SET
          to.taggerAt = tag_data.taggerAt,
          to.message = tag_data.message
        ON MATCH SET
          to.taggerAt = tag_data.taggerAt,
          to.message = tag_data.message

        MERGE (target:Commit {commit_hash: tag_data.targetSha})
        MERGE (to)-[:TAG_OF]->(target)

        MERGE (tagger:Identity {source: tag_data.tagger.source, name: tag_data.tagger.name, email: tag_data.tagger.email})
        MERGE (tagger)-[:TAGGED]->(to)

        MERGE (r:Ref {kind: 'tag', name: tag_data.name, remote: ''})
        MERGE (r)-[:POINTS_TO]->(to)
        """
        tx.run(query, tags=tags)

    def batch_create_events(self, events: List[Dict[str, Any]]):
        """
        Batch create Event nodes (scaffolding for future multi-source integration).
        
        Args:
            events: List of dicts with keys: type, source, ts, artifact_type (optional), artifact_id (optional)
        """
        with self._driver.session() as session:
            session.execute_write(self._batch_create_events_tx, events)

    @staticmethod
    def _batch_create_events_tx(tx, events: List[Dict[str, Any]]):
        """Transaction function for batch event creation (Neo4j 4.x compatible)."""
        # Neo4j 4.x doesn't support CALL subqueries with WHERE, so we use conditional matching
        query = """
        UNWIND $events AS event_data
        
        MERGE (e:Event {type: event_data.type, source: event_data.source, ts: event_data.ts})
        SET e.ts = event_data.ts
        
        WITH e, event_data
        WHERE event_data.artifact_type IS NOT NULL 
          AND event_data.artifact_id IS NOT NULL
          AND event_data.artifact_type = 'Commit'
        
        MATCH (a:Commit {commit_hash: event_data.artifact_id})
        MERGE (e)-[:ABOUT]->(a)
        """
        tx.run(query, events=events)

    def create_role(self, person_id: str, role_kind: str, from_date: datetime, to_date: Optional[datetime], source: str):
        """
        Create a Role relationship (scaffolding for temporal authority tracking).
        
        Args:
            person_id: Person node ID
            role_kind: Type of role ("maintainer", "keyholder", "reviewer")
            from_date: Start date
            to_date: End date (optional)
            source: Source of role information (e.g., "keyring", "repo_acl")
        """
        with self._driver.session() as session:
            session.run(
                """
                MATCH (p:Person {id: $person_id})
                MERGE (r:Role {kind: $role_kind})
                MERGE (p)-[hr:HELD_ROLE]->(r)
                SET hr.from = $from_date,
                    hr.to = $to_date,
                    hr.source = $source
                """,
                person_id=person_id,
                role_kind=role_kind,
                from_date=from_date,
                to_date=to_date,
                source=source
            )

    def batch_upsert_pgp_keys(self, key_rows: List[Dict[str, Any]], batch_size: int = 1000):
        """
        Batch upsert PGPKey nodes.
        
        Args:
            key_rows: List of dicts with keys: fingerprint, createdAt (optional), revokedAt (optional)
            batch_size: Number of keys to process per transaction
        """
        if not key_rows:
            return
        
        for i in range(0, len(key_rows), batch_size):
            batch = key_rows[i:i + batch_size]
            with self._driver.session() as session:
                session.execute_write(self._batch_upsert_pgp_keys_tx, batch)
            if len(key_rows) > batch_size:
                logger.info(f"Processed PGP key batch {i//batch_size + 1}/{(len(key_rows)-1)//batch_size + 1}")

    @staticmethod
    def _batch_upsert_pgp_keys_tx(tx, rows: List[Dict[str, Any]]):
        """Transaction function for batch PGP key upsert."""
        query = """
        UNWIND $rows AS row

        MERGE (k:PGPKey {fingerprint: row.fingerprint})
        ON CREATE SET
          k.createdAt = row.createdAt,
          k.revokedAt = row.revokedAt
        ON MATCH SET
          k.createdAt = coalesce(row.createdAt, k.createdAt),
          k.revokedAt = coalesce(row.revokedAt, k.revokedAt)
        """
        tx.run(query, rows=rows)

    def batch_create_signatures(
        self, 
        signature_rows: List[Dict[str, Any]], 
        batch_size: int = 1000
    ):
        """
        Batch create HAS_SIGNATURE relationships.
        
        Args:
            signature_rows: List of dicts with keys:
                - artifact_type: "Commit" or "TagObject"
                - artifact_id: commit_hash or tag name
                - fingerprint: PGP key fingerprint
                - valid: boolean or None
                - method: "gpg"
            batch_size: Number of signatures to process per transaction
        """
        if not signature_rows:
            return
        
        for i in range(0, len(signature_rows), batch_size):
            batch = signature_rows[i:i + batch_size]
            with self._driver.session() as session:
                session.execute_write(self._batch_create_signatures_tx, batch)
            if len(signature_rows) > batch_size:
                logger.info(f"Processed signature batch {i//batch_size + 1}/{(len(signature_rows)-1)//batch_size + 1}")

    @staticmethod
    def _batch_create_signatures_tx(tx, rows: List[Dict[str, Any]]):
        """Transaction function for batch signature creation (Neo4j 4.x compatible)."""
        # Process commits and tags separately for compatibility
        commit_rows = [r for r in rows if r.get('artifact_type') == 'Commit']
        tag_rows = [r for r in rows if r.get('artifact_type') == 'TagObject']
        
        # Process commits
        if commit_rows:
            query_commits = """
            UNWIND $rows AS row
            MATCH (artifact:Commit {commit_hash: row.artifact_id})
            MERGE (k:PGPKey {fingerprint: row.fingerprint})
            MERGE (artifact)-[hs:HAS_SIGNATURE]->(k)
            SET hs.valid = row.valid,
                hs.method = row.method,
                hs.signer_fp = row.fingerprint
            """
            tx.run(query_commits, rows=commit_rows)
        
        # Process tags
        if tag_rows:
            query_tags = """
            UNWIND $rows AS row
            MATCH (artifact:TagObject {name: row.artifact_id})
            MERGE (k:PGPKey {fingerprint: row.fingerprint})
            MERGE (artifact)-[hs:HAS_SIGNATURE]->(k)
            SET hs.valid = row.valid,
                hs.method = row.method,
                hs.signer_fp = row.fingerprint
            """
            tx.run(query_tags, rows=tag_rows)

    def batch_mark_commits_checked_for_signatures(self, commit_shas: List[str], batch_size: int = 1000):
        """
        Mark commits as checked for signatures (even if they don't have signatures).
        This allows us to skip already-checked commits on subsequent runs.
        
        Args:
            commit_shas: List of commit hashes to mark as checked
            batch_size: Number of commits to process per transaction
        """
        if not commit_shas:
            return
        
        for i in range(0, len(commit_shas), batch_size):
            batch = commit_shas[i:i + batch_size]
            with self._driver.session() as session:
                session.execute_write(self._batch_mark_commits_checked_tx, batch)
            if len(commit_shas) > batch_size:
                logger.info(f"Marked {min(i + batch_size, len(commit_shas))}/{len(commit_shas)} commits as checked")

    @staticmethod
    def _batch_mark_commits_checked_tx(tx, commit_shas: List[str]):
        """Transaction function for marking commits as checked for signatures."""
        query = """
        UNWIND $commit_shas AS sha
        MATCH (c:Commit {commit_hash: sha})
        SET c.signature_checked = true
        """
        tx.run(query, commit_shas=commit_shas)

    def batch_create_merged_includes(
        self,
        merge_rows: List[Dict[str, Any]],
        batch_size: int = 1000
    ):
        """
        Batch create MERGED_INCLUDES relationships.
        
        Args:
            merge_rows: List of dicts with keys:
                - merge_sha: SHA of merge commit
                - included_shas: List of commit SHAs introduced by merge
            batch_size: Number of merges to process per transaction
        """
        if not merge_rows:
            return
        
        for i in range(0, len(merge_rows), batch_size):
            batch = merge_rows[i:i + batch_size]
            with self._driver.session() as session:
                session.execute_write(self._batch_create_merged_includes_tx, batch)
            if len(merge_rows) > batch_size:
                logger.info(f"Processed MERGED_INCLUDES batch {i//batch_size + 1}/{(len(merge_rows)-1)//batch_size + 1}")

    @staticmethod
    def _batch_create_merged_includes_tx(tx, rows: List[Dict[str, Any]]):
        """Transaction function for batch MERGED_INCLUDES creation."""
        query = """
        UNWIND $rows AS row
        MATCH (merge:Commit {commit_hash: row.merge_sha})
        WHERE merge.isMerge = true
        
        UNWIND row.included_shas AS included_sha
        MATCH (included:Commit {commit_hash: included_sha})
        MERGE (merge)-[:MERGED_INCLUDES]->(included)
        """
        tx.run(query, rows=rows)

    def get_identity_stats(self, email: str, source: str = "git") -> Optional[Dict[str, Any]]:
        """Get statistics for an identity including signed/unsigned commits."""
        with self.driver.session() as session:
            # First get commit-level stats
            query = """
            MATCH (i:Identity {email: $email, source: $source})-[r:AUTHORED|COMMITTED]->(c:Commit)
            OPTIONAL MATCH (c)-[:HAS_SIGNATURE]->(pgp:PGPKey)
            OPTIONAL MATCH (e:Event)-[:ABOUT]->(c)
            WHERE e.type = 'commit_authored' AND e.source = 'git'
            WITH DISTINCT c, 
                 CASE WHEN pgp IS NOT NULL THEN 1 ELSE 0 END as isSigned,
                 COALESCE(e.ts, c.authoredAt) as commitDate
            RETURN 
                count(c) as totalCommits,
                sum(isSigned) as signedCommits,
                count(c) - sum(isSigned) as unsignedCommits,
                min(commitDate) as firstCommitDate,
                max(commitDate) as lastCommitDate
            """
            result = session.run(query, email=email, source=source)
            commitRecord = result.single()
            if not commitRecord or commitRecord["totalCommits"] == 0:
                return None

            # Then get file change stats
            fileQuery = """
            MATCH (i:Identity {email: $email, source: $source})-[r:AUTHORED|COMMITTED]->(c:Commit)
            MATCH (c)-[:HAS_CHANGE]->(fc:FileChange)
            RETURN 
                sum(fc.add) as totalLinesAdded,
                sum(fc.del) as totalLinesDeleted,
                count(DISTINCT CASE WHEN fc.status = 'A' THEN fc.path END) as filesCreated
            """
            fileResult = session.run(fileQuery, email=email, source=source)
            fileRecord = fileResult.single()
            
            total_commits = commitRecord["totalCommits"]
            signed_commits = commitRecord["signedCommits"] or 0
            signed_percentage = (signed_commits / total_commits * 100) if total_commits > 0 else 0.0
            
            # Format dates
            first_date = commitRecord["firstCommitDate"]
            last_date = commitRecord["lastCommitDate"]
            if first_date:
                if isinstance(first_date, datetime):
                    first_date = first_date.isoformat()
                elif hasattr(first_date, 'to_native'):
                    first_date = first_date.to_native().isoformat()
                else:
                    first_date = str(first_date)
            if last_date:
                if isinstance(last_date, datetime):
                    last_date = last_date.isoformat()
                elif hasattr(last_date, 'to_native'):
                    last_date = last_date.to_native().isoformat()
                else:
                    last_date = str(last_date)
            
            return {
                "totalCommits": total_commits,
                "totalLinesAdded": (fileRecord["totalLinesAdded"] or 0) if fileRecord else 0,
                "totalLinesDeleted": (fileRecord["totalLinesDeleted"] or 0) if fileRecord else 0,
                "filesCreated": (fileRecord["filesCreated"] or 0) if fileRecord else 0,
                "firstCommitDate": first_date or "",
                "lastCommitDate": last_date or "",
                "signedCommits": signed_commits,
                "unsignedCommits": commitRecord["unsignedCommits"] or 0,
                "signedPercentage": round(signed_percentage, 2)
            }
            result = session.run(query, email=email, source=source)
            record = result.single()
            if not record or record["totalCommits"] == 0:
                return None
            
            total_commits = record["totalCommits"]
            signed_commits = record["signedCommits"] or 0
            signed_percentage = (signed_commits / total_commits * 100) if total_commits > 0 else 0.0
            
            # Format dates
            first_date = record["firstCommitDate"]
            last_date = record["lastCommitDate"]
            if first_date:
                if isinstance(first_date, datetime):
                    first_date = first_date.isoformat()
                elif hasattr(first_date, 'to_native'):
                    first_date = first_date.to_native().isoformat()
                else:
                    first_date = str(first_date)
            if last_date:
                if isinstance(last_date, datetime):
                    last_date = last_date.isoformat()
                elif hasattr(last_date, 'to_native'):
                    last_date = last_date.to_native().isoformat()
                else:
                    last_date = str(last_date)
            
            return {
                "totalCommits": total_commits,
                "totalLinesAdded": record["totalLinesAdded"] or 0,
                "totalLinesDeleted": record["totalLinesDeleted"] or 0,
                "filesCreated": record["filesCreated"] or 0,
                "firstCommitDate": first_date or "",
                "lastCommitDate": last_date or "",
                "signedCommits": signed_commits,
                "unsignedCommits": record["unsignedCommits"] or 0,
                "signedPercentage": round(signed_percentage, 2)
            }

    def get_identity_commits_over_time(self, email: str, source: str = "git", timeBucket: str = "month") -> List[Dict[str, Any]]:
        """Get commits over time for an identity using Event nodes."""
        with self.driver.session() as session:
            if timeBucket == "year":
                query = """
                MATCH (i:Identity {email: $email, source: $source})-[r:AUTHORED|COMMITTED]->(c:Commit)
                OPTIONAL MATCH (e:Event)-[:ABOUT]->(c)
                WHERE e.type = 'commit_authored' AND e.source = 'git'
                WITH c, COALESCE(e.ts, c.authoredAt) as ts
                WHERE ts IS NOT NULL
                WITH datetime({year: ts.year, month: 1, day: 1}) as bucket_date, 
                     toString(ts.year) + '-01-01' as period,
                     count(DISTINCT c) as count
                ORDER BY bucket_date
                RETURN period, count, toString(bucket_date) as date
                """
            else:  # default to month
                query = """
                MATCH (i:Identity {email: $email, source: $source})-[r:AUTHORED|COMMITTED]->(c:Commit)
                OPTIONAL MATCH (e:Event)-[:ABOUT]->(c)
                WHERE e.type = 'commit_authored' AND e.source = 'git'
                WITH c, COALESCE(e.ts, c.authoredAt) as ts
                WHERE ts IS NOT NULL
                WITH datetime({year: ts.year, month: ts.month, day: 1}) as bucket_date,
                     toString(ts.year) + '-' + 
                     CASE WHEN ts.month < 10 THEN '0' + toString(ts.month) ELSE toString(ts.month) END + 
                     '-01' as period,
                     count(DISTINCT c) as count
                ORDER BY bucket_date
                RETURN period, count, toString(bucket_date) as date
                """
            result = session.run(query, email=email, source=source)
            buckets = []
            for record in result:
                date_str = record["date"]
                # Format date string if needed
                if date_str and 'T' in date_str:
                    date_str = date_str.split('T')[0]
                buckets.append({
                    "period": record["period"],
                    "count": record["count"],
                    "date": date_str or record["period"]
                })
            return buckets

    def get_identity_top_files(self, email: str, source: str = "git", limit: int = 10) -> List[Dict[str, Any]]:
        """Get top files contributed to by an identity."""
        with self.driver.session() as session:
            query = """
            MATCH (i:Identity {email: $email, source: $source})-[r:AUTHORED|COMMITTED]->(c:Commit)
            MATCH (c)-[:HAS_CHANGE]->(fc:FileChange)-[:OF_PATH]->(p:Path)
            WITH p.path as path, 
                 sum(fc.add) as linesAdded,
                 sum(fc.del) as linesDeleted,
                 sum(fc.add + fc.del) as totalChanges,
                 count(DISTINCT c) as commitCount
            ORDER BY totalChanges DESC
            LIMIT $limit
            RETURN path, linesAdded, linesDeleted, totalChanges, commitCount
            """
            result = session.run(query, email=email, source=source, limit=limit)
            files = []
            for record in result:
                files.append({
                    "path": record["path"],
                    "linesAdded": record["linesAdded"] or 0,
                    "linesDeleted": record["linesDeleted"] or 0,
                    "totalChanges": record["totalChanges"] or 0,
                    "commitCount": record["commitCount"]
                })
            return files

    def get_repository_stats(self, repositoryUrl: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get statistics for a repository."""
        with self.driver.session() as session:
            # Get commit and signature stats
            commitQuery = """
            MATCH (c:Commit)
            OPTIONAL MATCH (c)-[:HAS_SIGNATURE]->(pgp:PGPKey)
            OPTIONAL MATCH (e:Event)-[:ABOUT]->(c)
            WHERE e.type = 'commit_authored' AND e.source = 'git'
            WITH DISTINCT c,
                 CASE WHEN pgp IS NOT NULL THEN 1 ELSE 0 END as isSigned,
                 COALESCE(e.ts, c.authoredAt) as commitDate
            RETURN 
                count(c) as totalCommits,
                sum(isSigned) as signedCommits,
                count(c) - sum(isSigned) as unsignedCommits,
                min(commitDate) as firstCommitDate,
                max(commitDate) as lastCommitDate
            """
            commitResult = session.run(commitQuery)
            commitRecord = commitResult.single()
            if not commitRecord or commitRecord["totalCommits"] == 0:
                return None

            # Get file and contributor stats
            fileQuery = """
            MATCH (c:Commit)
            OPTIONAL MATCH (c)-[:HAS_CHANGE]->(fc:FileChange)-[:OF_PATH]->(p:Path)
            OPTIONAL MATCH (i:Identity)-[:AUTHORED|COMMITTED]->(c)
            RETURN 
                count(DISTINCT p) as totalFiles,
                count(DISTINCT i) as totalContributors
            """
            fileResult = session.run(fileQuery)
            fileRecord = fileResult.single()
            total_commits = commitRecord["totalCommits"]
            signed_commits = commitRecord["signedCommits"] or 0
            signed_percentage = (signed_commits / total_commits * 100) if total_commits > 0 else 0.0
            
            # Format dates
            first_date = commitRecord["firstCommitDate"]
            last_date = commitRecord["lastCommitDate"]
            if first_date:
                if isinstance(first_date, datetime):
                    first_date = first_date.isoformat()
                elif hasattr(first_date, 'to_native'):
                    first_date = first_date.to_native().isoformat()
                else:
                    first_date = str(first_date)
            if last_date:
                if isinstance(last_date, datetime):
                    last_date = last_date.isoformat()
                elif hasattr(last_date, 'to_native'):
                    last_date = last_date.to_native().isoformat()
                else:
                    last_date = str(last_date)
            
            return {
                "totalCommits": total_commits,
                "totalFiles": (fileRecord["totalFiles"] or 0) if fileRecord else 0,
                "totalLinesOfCode": 0,  # Approximate - would need to calculate from file changes
                "totalContributors": (fileRecord["totalContributors"] or 0) if fileRecord else 0,
                "firstCommitDate": first_date or "",
                "lastCommitDate": last_date or "",
                "signedCommits": signed_commits,
                "unsignedCommits": commitRecord["unsignedCommits"] or 0,
                "signedPercentage": round(signed_percentage, 2)
            }

    def get_repository_commits_over_time(self, repositoryUrl: Optional[str] = None, timeBucket: str = "month") -> List[Dict[str, Any]]:
        """Get commits over time for a repository using Event nodes."""
        with self.driver.session() as session:
            if timeBucket == "year":
                query = """
                MATCH (c:Commit)
                OPTIONAL MATCH (e:Event)-[:ABOUT]->(c)
                WHERE e.type = 'commit_authored' AND e.source = 'git'
                WITH c, COALESCE(e.ts, c.authoredAt) as ts
                WHERE ts IS NOT NULL
                WITH datetime({year: ts.year, month: 1, day: 1}) as bucket_date,
                     toString(ts.year) + '-01-01' as period,
                     count(DISTINCT c) as count
                ORDER BY bucket_date
                RETURN period, count, toString(bucket_date) as date
                """
            else:  # default to month
                query = """
                MATCH (c:Commit)
                OPTIONAL MATCH (e:Event)-[:ABOUT]->(c)
                WHERE e.type = 'commit_authored' AND e.source = 'git'
                WITH c, COALESCE(e.ts, c.authoredAt) as ts
                WHERE ts IS NOT NULL
                WITH datetime({year: ts.year, month: ts.month, day: 1}) as bucket_date,
                     toString(ts.year) + '-' + 
                     CASE WHEN ts.month < 10 THEN '0' + toString(ts.month) ELSE toString(ts.month) END + 
                     '-01' as period,
                     count(DISTINCT c) as count
                ORDER BY bucket_date
                RETURN period, count, toString(bucket_date) as date
                """
            result = session.run(query)
            buckets = []
            for record in result:
                date_str = record["date"]
                # Format date string if needed
                if date_str and 'T' in date_str:
                    date_str = date_str.split('T')[0]
                buckets.append({
                    "period": record["period"],
                    "count": record["count"],
                    "date": date_str or record["period"]
                })
            return buckets

    def get_file_stats(self, filePath: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a file."""
        with self.driver.session() as session:
            query = """
            MATCH (p:Path {path: $filePath})<-[:OF_PATH]-(fc:FileChange)<-[:HAS_CHANGE]-(c:Commit)
            OPTIONAL MATCH (e:Event)-[:ABOUT]->(c)
            WHERE e.type = 'commit_authored' AND e.source = 'git'
            OPTIONAL MATCH (i:Identity)-[:AUTHORED|COMMITTED]->(c)
            WITH c, fc, e, i
            RETURN 
                count(DISTINCT c) as totalCommits,
                count(DISTINCT i) as totalContributors,
                min(CASE WHEN e IS NOT NULL THEN e.ts ELSE c.authoredAt END) as firstCommitDate,
                max(CASE WHEN e IS NOT NULL THEN e.ts ELSE c.authoredAt END) as lastCommitDate,
                sum(fc.add) as totalLinesAdded,
                sum(fc.del) as totalLinesDeleted
            """
            result = session.run(query, filePath=filePath)
            record = result.single()
            if not record or record["totalCommits"] == 0:
                return None
            
            # Format dates
            first_date = record["firstCommitDate"]
            last_date = record["lastCommitDate"]
            if first_date:
                if isinstance(first_date, datetime):
                    first_date = first_date.isoformat()
                elif hasattr(first_date, 'to_native'):
                    first_date = first_date.to_native().isoformat()
                else:
                    first_date = str(first_date)
            if last_date:
                if isinstance(last_date, datetime):
                    last_date = last_date.isoformat()
                elif hasattr(last_date, 'to_native'):
                    last_date = last_date.to_native().isoformat()
                else:
                    last_date = str(last_date)
            
            return {
                "totalCommits": record["totalCommits"],
                "totalContributors": record["totalContributors"] or 0,
                "firstCommitDate": first_date or "",
                "lastCommitDate": last_date or "",
                "totalLinesAdded": record["totalLinesAdded"] or 0,
                "totalLinesDeleted": record["totalLinesDeleted"] or 0
            }

    def get_file_commits_over_time(self, filePath: str, timeBucket: str = "month") -> List[Dict[str, Any]]:
        """Get commits over time for a file using Event nodes."""
        with self.driver.session() as session:
            if timeBucket == "year":
                query = """
                MATCH (p:Path {path: $filePath})<-[:OF_PATH]-(fc:FileChange)<-[:HAS_CHANGE]-(c:Commit)
                OPTIONAL MATCH (e:Event)-[:ABOUT]->(c)
                WHERE e.type = 'commit_authored' AND e.source = 'git'
                WITH c, COALESCE(e.ts, c.authoredAt) as ts
                WHERE ts IS NOT NULL
                WITH datetime({year: ts.year, month: 1, day: 1}) as bucket_date,
                     toString(ts.year) + '-01-01' as period,
                     count(DISTINCT c) as count
                ORDER BY bucket_date
                RETURN period, count, toString(bucket_date) as date
                """
            else:  # default to month
                query = """
                MATCH (p:Path {path: $filePath})<-[:OF_PATH]-(fc:FileChange)<-[:HAS_CHANGE]-(c:Commit)
                OPTIONAL MATCH (e:Event)-[:ABOUT]->(c)
                WHERE e.type = 'commit_authored' AND e.source = 'git'
                WITH c, COALESCE(e.ts, c.authoredAt) as ts
                WHERE ts IS NOT NULL
                WITH datetime({year: ts.year, month: ts.month, day: 1}) as bucket_date,
                     toString(ts.year) + '-' + 
                     CASE WHEN ts.month < 10 THEN '0' + toString(ts.month) ELSE toString(ts.month) END + 
                     '-01' as period,
                     count(DISTINCT c) as count
                ORDER BY bucket_date
                RETURN period, count, toString(bucket_date) as date
                """
            result = session.run(query, filePath=filePath)
            buckets = []
            for record in result:
                date_str = record["date"]
                # Format date string if needed
                if date_str and 'T' in date_str:
                    date_str = date_str.split('T')[0]
                buckets.append({
                    "period": record["period"],
                    "count": record["count"],
                    "date": date_str or record["period"]
                })
            return buckets

    def get_file_contributors(self, filePath: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top contributors to a file."""
        with self.driver.session() as session:
            query = """
            MATCH (p:Path {path: $filePath})<-[:OF_PATH]-(fc:FileChange)<-[:HAS_CHANGE]-(c:Commit)
            MATCH (i:Identity)-[:AUTHORED|COMMITTED]->(c)
            WITH i, 
                 count(DISTINCT c) as commitCount,
                 sum(fc.add) as linesAdded,
                 sum(fc.del) as linesDeleted
            ORDER BY commitCount DESC
            LIMIT $limit
            RETURN i.name as name, i.email as email, i.source as source, commitCount, linesAdded, linesDeleted
            """
            result = session.run(query, filePath=filePath, limit=limit)
            contributors = []
            for record in result:
                contributors.append({
                    "identity": {
                        "name": record["name"],
                        "email": record["email"],
                        "source": record["source"]
                    },
                    "commitCount": record["commitCount"],
                    "linesAdded": record["linesAdded"] or 0,
                    "linesDeleted": record["linesDeleted"] or 0
                })
            return contributors

    def get_all_file_paths(self, limit: Optional[int] = None) -> List[str]:
        """Get all file paths from Path nodes."""
        with self.driver.session() as session:
            query = """
            MATCH (p:Path)
            RETURN p.path as path
            ORDER BY p.path
            """
            if limit:
                query += f" LIMIT {limit}"
            result = session.run(query)
            paths = [record["path"] for record in result]
            return paths

    def get_pgp_signature_stats(self) -> Dict[str, Any]:
        """Get PGP signature statistics including unique keys count."""
        with self.driver.session() as session:
            query = """
            MATCH (k:PGPKey)
            RETURN count(DISTINCT k) as uniqueKeys
            """
            result = session.run(query)
            record = result.single()
            unique_keys = record["uniqueKeys"] or 0 if record else 0
            
            return {
                "uniqueKeys": unique_keys
            }

    def get_repository_top_signers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top signers by number of signed commits."""
        with self.driver.session() as session:
            query = """
            MATCH (i:Identity {source: "git"})-[r:AUTHORED|COMMITTED]->(c:Commit)-[:HAS_SIGNATURE]->(k:PGPKey)
            WITH i, count(DISTINCT c) as signedCommitCount
            ORDER BY signedCommitCount DESC
            LIMIT $limit
            RETURN i.name as name, i.email as email, i.source as source, signedCommitCount
            """
            result = session.run(query, limit=limit)
            signers = []
            for record in result:
                signers.append({
                    "identity": {
                        "name": record["name"],
                        "email": record["email"],
                        "source": record["source"]
                    },
                    "signedCommitCount": record["signedCommitCount"]
                })
            return signers

    def get_repository_signature_adoption_trend(self, timeBucket: str = "month") -> List[Dict[str, Any]]:
        """Get signature adoption trend over time (percentage of commits signed per time period)."""
        with self.driver.session() as session:
            if timeBucket == "year":
                query = """
                MATCH (c:Commit)
                OPTIONAL MATCH (c)-[:HAS_SIGNATURE]->(k:PGPKey)
                OPTIONAL MATCH (e:Event)-[:ABOUT]->(c)
                WHERE e.type = 'commit_authored' AND e.source = 'git'
                WITH c, 
                     CASE WHEN k IS NOT NULL THEN 1 ELSE 0 END as isSigned,
                     COALESCE(e.ts, c.authoredAt) as ts
                WHERE ts IS NOT NULL
                WITH datetime({year: ts.year, month: 1, day: 1}) as bucket_date,
                     toString(ts.year) + '-01-01' as period,
                     count(c) as totalCommits,
                     sum(isSigned) as signedCommits
                ORDER BY bucket_date
                RETURN period, totalCommits, signedCommits, 
                       CASE WHEN totalCommits > 0 THEN (toFloat(signedCommits) / toFloat(totalCommits) * 100.0) ELSE 0.0 END as signedPercentage,
                       toString(bucket_date) as date
                """
            else:  # default to month
                query = """
                MATCH (c:Commit)
                OPTIONAL MATCH (c)-[:HAS_SIGNATURE]->(k:PGPKey)
                OPTIONAL MATCH (e:Event)-[:ABOUT]->(c)
                WHERE e.type = 'commit_authored' AND e.source = 'git'
                WITH c, 
                     CASE WHEN k IS NOT NULL THEN 1 ELSE 0 END as isSigned,
                     COALESCE(e.ts, c.authoredAt) as ts
                WHERE ts IS NOT NULL
                WITH datetime({year: ts.year, month: ts.month, day: 1}) as bucket_date,
                     toString(ts.year) + '-' + 
                     CASE WHEN ts.month < 10 THEN '0' + toString(ts.month) ELSE toString(ts.month) END + 
                     '-01' as period,
                     count(c) as totalCommits,
                     sum(isSigned) as signedCommits
                ORDER BY bucket_date
                RETURN period, totalCommits, signedCommits, 
                       CASE WHEN totalCommits > 0 THEN (toFloat(signedCommits) / toFloat(totalCommits) * 100.0) ELSE 0.0 END as signedPercentage,
                       toString(bucket_date) as date
                """
            result = session.run(query)
            buckets = []
            for record in result:
                date_str = record["date"]
                # Format date string if needed
                if date_str and 'T' in date_str:
                    date_str = date_str.split('T')[0]
                buckets.append({
                    "period": record["period"],
                    "totalCommits": record["totalCommits"] or 0,
                    "signedCommits": record["signedCommits"] or 0,
                    "signedPercentage": round(record["signedPercentage"] or 0.0, 2),
                    "date": date_str or record["period"]
                })
            return buckets

    def get_repository_health_metrics(self) -> Dict[str, Any]:
        """Get repository health metrics including average commits per contributor, average time between commits, and most active period."""
        with self.driver.session() as session:
            # Get total commits and contributors
            statsQuery = """
            MATCH (c:Commit)
            OPTIONAL MATCH (i:Identity {source: "git"})-[r:AUTHORED|COMMITTED]->(c)
            OPTIONAL MATCH (e:Event)-[:ABOUT]->(c)
            WHERE e.type = 'commit_authored' AND e.source = 'git'
            WITH count(DISTINCT c) as totalCommits,
                 count(DISTINCT i) as totalContributors
            RETURN totalCommits, totalContributors
            """
            statsResult = session.run(statsQuery)
            statsRecord = statsResult.single()
            
            total_commits = statsRecord["totalCommits"] or 0
            total_contributors = statsRecord["totalContributors"] or 0
            avg_commits_per_contributor = (total_commits / total_contributors) if total_contributors > 0 else 0.0

            # Get commit timestamps for time between commits calculation
            timeQuery = """
            MATCH (c:Commit)
            OPTIONAL MATCH (e:Event)-[:ABOUT]->(c)
            WHERE e.type = 'commit_authored' AND e.source = 'git'
            WITH c, COALESCE(e.ts, c.authoredAt) as commitDate
            WHERE commitDate IS NOT NULL
            RETURN commitDate
            ORDER BY commitDate
            """
            timeResult = session.run(timeQuery)
            commit_dates = []
            for record in timeResult:
                commit_date = record["commitDate"]
                if isinstance(commit_date, datetime):
                    commit_dates.append(commit_date)
                elif hasattr(commit_date, 'to_native'):
                    commit_dates.append(commit_date.to_native())
                else:
                    try:
                        commit_dates.append(datetime.fromisoformat(str(commit_date).replace('Z', '+00:00')))
                    except:
                        pass

            # Calculate average time between commits
            avg_time_between_commits = 0.0
            if len(commit_dates) > 1:
                total_seconds = 0
                for i in range(1, len(commit_dates)):
                    diff = (commit_dates[i] - commit_dates[i-1]).total_seconds()
                    total_seconds += diff
                avg_time_between_commits = total_seconds / (len(commit_dates) - 1) if len(commit_dates) > 1 else 0.0

            # Get most active period (month/year with most commits)
            activePeriodQuery = """
            MATCH (c:Commit)
            OPTIONAL MATCH (e:Event)-[:ABOUT]->(c)
            WHERE e.type = 'commit_authored' AND e.source = 'git'
            WITH c, COALESCE(e.ts, c.authoredAt) as ts
            WHERE ts IS NOT NULL
            WITH datetime({year: ts.year, month: ts.month, day: 1}) as bucket_date,
                 toString(ts.year) + '-' + 
                 CASE WHEN ts.month < 10 THEN '0' + toString(ts.month) ELSE toString(ts.month) END + 
                 '-01' as period,
                 count(DISTINCT c) as commitCount
            ORDER BY commitCount DESC
            LIMIT 1
            RETURN period, commitCount, toString(bucket_date) as date
            """
            activeResult = session.run(activePeriodQuery)
            activeRecord = activeResult.single()
            
            most_active_period = ""
            most_active_commits = 0
            if activeRecord:
                most_active_period = activeRecord["period"] or ""
                most_active_commits = activeRecord["commitCount"] or 0
                # Format the period nicely
                if most_active_period:
                    try:
                        date_obj = datetime.fromisoformat(most_active_period.replace('Z', '+00:00'))
                        most_active_period = date_obj.strftime("%B %Y")
                    except:
                        pass

            return {
                "averageCommitsPerContributor": round(avg_commits_per_contributor, 2),
                "averageTimeBetweenCommits": round(avg_time_between_commits, 0),  # in seconds
                "mostActivePeriod": most_active_period,
                "mostActivePeriodCommits": most_active_commits
            }

    def get_repository_top_contributors(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top contributors by commit count for the repository."""
        with self.driver.session() as session:
            query = """
            MATCH (i:Identity {source: "git"})-[r:AUTHORED|COMMITTED]->(c:Commit)
            WITH i, count(DISTINCT c) as commitCount
            ORDER BY commitCount DESC
            LIMIT $limit
            RETURN i.name as name, i.email as email, i.source as source, commitCount
            """
            result = session.run(query, limit=limit)
            contributors = []
            for record in result:
                contributors.append({
                    "identity": {
                        "name": record["name"],
                        "email": record["email"],
                        "source": record["source"]
                    },
                    "commitCount": record["commitCount"]
                })
            return contributors

    def get_repository_most_active_files(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most active files by commit count for the repository."""
        with self.driver.session() as session:
            query = """
            MATCH (c:Commit)-[:HAS_CHANGE]->(fc:FileChange)-[:OF_PATH]->(p:Path)
            OPTIONAL MATCH (i:Identity)-[:AUTHORED|COMMITTED]->(c)
            WITH p.path as path, 
                 count(DISTINCT c) as commitCount,
                 count(DISTINCT i) as contributorCount
            ORDER BY commitCount DESC
            LIMIT $limit
            RETURN path, commitCount, contributorCount
            """
            result = session.run(query, limit=limit)
            files = []
            for record in result:
                files.append({
                    "path": record["path"],
                    "commitCount": record["commitCount"],
                    "contributorCount": record["contributorCount"] or 0
                })
            return files

    def get_repository_contributor_growth(self, timeBucket: str = "month") -> List[Dict[str, Any]]:
        """Get contributor growth over time (new contributors per time period)."""
        with self.driver.session() as session:
            if timeBucket == "year":
                query = """
                MATCH (i:Identity {source: "git"})-[r:AUTHORED|COMMITTED]->(c:Commit)
                OPTIONAL MATCH (e:Event)-[:ABOUT]->(c)
                WHERE e.type = 'commit_authored' AND e.source = 'git'
                WITH i, c, COALESCE(e.ts, c.authoredAt) as ts
                WHERE ts IS NOT NULL
                WITH i, min(ts) as firstCommitDate
                WITH datetime({year: firstCommitDate.year, month: 1, day: 1}) as bucket_date,
                     toString(firstCommitDate.year) + '-01-01' as period,
                     count(DISTINCT i) as newContributors
                ORDER BY bucket_date
                RETURN period, newContributors, toString(bucket_date) as date
                """
            else:  # default to month
                query = """
                MATCH (i:Identity {source: "git"})-[r:AUTHORED|COMMITTED]->(c:Commit)
                OPTIONAL MATCH (e:Event)-[:ABOUT]->(c)
                WHERE e.type = 'commit_authored' AND e.source = 'git'
                WITH i, c, COALESCE(e.ts, c.authoredAt) as ts
                WHERE ts IS NOT NULL
                WITH i, min(ts) as firstCommitDate
                WITH datetime({year: firstCommitDate.year, month: firstCommitDate.month, day: 1}) as bucket_date,
                     toString(firstCommitDate.year) + '-' + 
                     CASE WHEN firstCommitDate.month < 10 THEN '0' + toString(firstCommitDate.month) ELSE toString(firstCommitDate.month) END + 
                     '-01' as period,
                     count(DISTINCT i) as newContributors
                ORDER BY bucket_date
                RETURN period, newContributors, toString(bucket_date) as date
                """
            result = session.run(query)
            buckets = []
            cumulative = 0
            for record in result:
                date_str = record["date"]
                # Format date string if needed
                if date_str and 'T' in date_str:
                    date_str = date_str.split('T')[0]
                new_contributors = record["newContributors"] or 0
                cumulative += new_contributors
                buckets.append({
                    "period": record["period"],
                    "newContributors": new_contributors,
                    "cumulativeContributors": cumulative,
                    "date": date_str or record["period"]
                })
            return buckets
