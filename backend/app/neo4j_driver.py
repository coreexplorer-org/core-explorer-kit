# src/neo4j_driver.py
from typing import Optional, List, Dict, Any
from datetime import datetime
from neo4j import GraphDatabase, Record
from commit_details import CommitDetails
import config
import time
import json
from git import Commit, Actor, Repo, TagReference
import uuid

def uuid4():  ## do we need this? 
    """Generate a random UUID."""
    return uuid.uuid4().hex


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
                print("Connected to Neo4j successfully.")
                break
            except Exception as e:
                print(f"Connection attempt {attempt + 1} failed: {e}")
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
            print("Database cleared.")

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
            print(f"merge actor ${properties.name}")
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
            result = session.run(
                """
                MATCH (r:GithubRepository)
                RETURN r.name AS name, r.url AS url, r.description AS description
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
            result = session.run(
                """
                MATCH (r:GithubRepository {url: $url})
                RETURN r.name AS name, r.url AS url, r.description AS description
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

    def create_constraints(self):
        """Create all required constraints for the new schema."""
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
            ]
            
            for constraint_query in constraints:
                try:
                    session.run(constraint_query)
                    print(f"Created constraint: {constraint_query[:50]}...")
                except Exception as e:
                    print(f"Constraint may already exist or error: {e}")
            
            # Indexes
            indexes = [
                "CREATE INDEX commit_times IF NOT EXISTS FOR (c:Commit) ON (c.committedAt)",
                "CREATE INDEX commit_authored_times IF NOT EXISTS FOR (c:Commit) ON (c.authoredAt)",
                "CREATE INDEX event_times IF NOT EXISTS FOR (e:Event) ON (e.ts)",
            ]
            
            for index_query in indexes:
                try:
                    session.run(index_query)
                    print(f"Created index: {index_query[:50]}...")
                except Exception as e:
                    print(f"Index may already exist or error: {e}")

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
            print(f"Processed commit batch {i//batch_size + 1}/{(len(commit_rows)-1)//batch_size + 1}")

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
            print(f"Processed file change batch {i//batch_size + 1}/{(len(change_rows)-1)//batch_size + 1}")

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
                SET ir.pulledAt = $pulled_at
                RETURN ir.id AS id
                """,
                run_id=run_id,
                pulled_at=pulled_at
            )
            record = result.single()
            return record["id"] if record else run_id

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
                print(f"Processed PGP key batch {i//batch_size + 1}/{(len(key_rows)-1)//batch_size + 1}")

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
                print(f"Processed signature batch {i//batch_size + 1}/{(len(signature_rows)-1)//batch_size + 1}")

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
                print(f"Marked {min(i + batch_size, len(commit_shas))}/{len(commit_shas)} commits as checked")

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
                print(f"Processed MERGED_INCLUDES batch {i//batch_size + 1}/{(len(merge_rows)-1)//batch_size + 1}")

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
