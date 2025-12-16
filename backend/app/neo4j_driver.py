# src/neo4j_driver.py
from typing import Optional
from neo4j import GraphDatabase, Record
from commit_details import CommitDetails
import config
import time
import json
from git import Commit, Actor
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
        self._auth = (user or config.NEO4J_USER, password or config.NEO4J_PASSWORD)
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
            RETURN elementId(a)
            """
            result = session.run(query, name=actor.name, email=actor.email)
            record = self._require_single_record(result, "Failed to create or retrieve node with label Actor")
            return record["elementId(a)"]

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

        # debugging the merge function in cypher
        # query = "MATCH (a:ImportStatus) RETURN a"

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
        self._driver.execute_query(
            "match (committer), (author)"
            "where elementId(author) = $author_id "
            "and elementId(committer) = $committer_id "
            "MERGE (c:Commit {commit_hash: $commit_hash}) "
            "ON CREATE SET c.parent_shas = $parent_shas, "
            " c.message = $message, "
            " c.summary = $summary "
            "MERGE (committer)-[cr:COMMITTED]->(c) "
            "ON CREATE SET cr.committed_date = $committed_date "
            "MERGE (author)-[ca:AUTHORED]->(c) "
            "ON CREATE SET ca.authored_date = $authored_date "
            , committer_id=committer_node,
              author_id=author_node,
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

    def get_node_count(self, label: str) -> int:
        """Get the count of nodes with a specific label."""
        # Validate label to prevent injection (alphanumeric and underscores only)
        if not label.replace("_", "").isalnum():
            raise ValueError(f"Invalid label: {label}. Labels must contain only alphanumeric characters and underscores.")
        with self.driver.session() as session:
            query = f"MATCH (n:{label}) RETURN count(n) AS count"
            result = session.run(query)  # type: ignore[arg-type]
            record = result.single()
            return record["count"] if record else 0

    def get_import_status(self):
        """Get the ImportStatus node details."""
        with self.driver.session() as session:
            query = "MATCH (i:ImportStatus) RETURN i"
            result = session.run(query)
            record = result.single()
            if record:
                return dict(record["i"])
            return None
