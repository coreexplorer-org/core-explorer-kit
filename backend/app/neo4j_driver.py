# src/neo4j_driver.py
from typing import Optional
from neo4j import GraphDatabase, Record
from commit_details import CommitDetails
import config
import time
import json
from git import Repo, Commit, Actor
import uuid

def uuid4():  ## do we need this? 
    """Generate a random UUID."""
    return uuid.uuid4().hex


class Neo4jDriver:
    def __init__(self, max_retries=5, retry_delay=2):
        self.driver = None
        for attempt in range(max_retries):
            try:
                self.driver = GraphDatabase.driver(
                    config.NEO4J_URI,
                    auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
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

    def clear_database(self):
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            print("Database cleared.")

    def create_node(self, label, properties):
        with self.driver.session() as session:
            query = f"MERGE (n:{label} $props) RETURN n"
            result = session.run(query, props=properties)
            return result.single()["n"]
    
    def tx_insert_actor(tx, actor) -> str:
        result = tx.run("""
            MERGE (a: Actor {name: $name, email: $email})
            RETURN a.email as email
            """,
            name=actor.name,
            email=actor.email
        )
        return result.single()["email"]

    def merge_actor(self, actor: Actor) -> Actor:
        with self.driver.session() as session:
            query = """
            MERGE (a:Actor {name: $name, email: $email})
            RETURN elementId(a)
            """
            result = session.run(query, name=actor.name, email=actor.email)
            return result.single()["elementId(a)"]

    def merge_actor_node(self, properties) -> Record:
        with self.driver.session() as session:
            query = "MERGE (n:Actor {name: $props.name, email: $props.email}) RETURN n"
            result = session.run(query, props=properties)
            print(f"merge actor ${properties.name}")
            return result.single()
        
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
            return result.single()["o"]

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
            return result.single()["r"]

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

    def merge_source(self, kind: str, name: str ):
        with self.driver.session() as session:
            result = session.run(
                """
                MERGE (s:Source {kind: $kind})
                ON CREATE SET s.name = $name
                RETURN s
                """,
                kind=kind,
                name=name
            )
            return result.single()["s"]

    def import_repository_job(self, repo_url: str, job_id: Optional[str] = None):
        if job_id is None:
            job_id = uuid4()

        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (r:GithubRepository {url: $repo_url})
                MERGE (s:Source {kind: 'GIT'})
                CREATE (j:Job {job_id: $job_id, created_at: datetime()})
                MERGE (j)<-[ib:IMPORTED_BY]-(r)
                MERGE (j)-[:IMPORTS_SOURCE]->(s)
                ON CREATE SET ib.import_job_scheduled = datetime()
                RETURN j
                """,
                repo_url=repo_url,
                job_id=job_id
            )
            return result.single()["j"]


    def start_job(self, job_id: str):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (j:Job {job_id: $job_id})
                SET j.started_at = datetime()
                RETURN j
                """,
                job_id=job_id
            )
            return result.single()["j"]

    def complete_job(self, job_id: str):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (j:Job {job_id: $job_id})
                SET j.completed_at = datetime()
                RETURN j
                """,
                job_id=job_id
            )
            return result.single()["j"]

    def get_unstarted_jobs_and_sources(self):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (j:Job)-[:IMPORTS_SOURCE]->(s:Source)
                WHERE NOT EXISTS(j.started_at)
                RETURN j.job_id AS job_id, s.kind AS kind, s.url AS url
                """
            )
            return [record.data() for record in result]

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
        with self.driver.session() as session:
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
        self.driver.execute_query(
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
        with self.driver.session() as session:
            result = session.execute_write(self._create_and_return_import_status_node)
            return result

    @staticmethod
    def _create_and_return_import_status_node(tx):
        query = """
        MERGE (a:ImportStatus)
        ON CREATE SET 
          a.git_import_complete = true,
          a.next_complete = false
        RETURN a.git_import_complete, a.next_complete
        """
        result = tx.run(query)
        record = result.single()
        return {
            "git_import_complete": record["a.git_import_complete"],
            "next_complete": record["a.next_complete"]
        }

if __name__ == "__main__":
    db = Neo4jDriver()
    # db.clear_database() # TODO make it clear again

    # Example usage: Process a repository
    repo_path = "downloaded_repo"  # Path to the local repository
    repo = Repo(repo_path)

    for commit in repo.iter_commits():
        db.merge_commit(commit)

    db.close()
