# src/neo4j_driver.py
from neo4j import GraphDatabase, Record
import config
import time
import json
from git import Repo, Commit, Actor


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

    def create_relationship(self, from_id, to_id, rel_type):
        with self.driver.session() as session:
            query = """
            MATCH (a), (b)
            WHERE id(a) = $from_id AND id(b) = $to_id
            CREATE (a)-[:%s]->(b)
            """ % rel_type
            session.run(query, from_id=from_id, to_id=to_id)

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

    def merge_organization(self, name: str, slug: str = None):
        slug = slug or name.lower().replace(" ", "-")
        with self.driver.session() as session:
            result = session.run(
                """
                MERGE (o:Organization {slug: $slug})
                ON CREATE SET o.name = $name
                RETURN o
                """,
                slug=slug,
                name=name
            )
            return result.single()["o"]

    def merge_repository(self, org_slug: str, name: str, url: str, description: str = ""):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (org:Organization {slug: $org_slug})
                MERGE (r:Repository {url: $url})
                ON CREATE SET r.name = $name, r.description = $description
                MERGE (org)-[:HAS_REPO]->(r)
                RETURN r
                """,
                org_slug=org_slug,
                name=name,
                url=url,
                description=description
            )
            return result.single()["r"]

    def import_repository_job(self, repo_url: str, run_id: str):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (r:Repository {url: $repo_url})
                MERGE (s:Source {kind: 'GIT', url: $repo_url})
                CREATE (j:Job {run_id: $run_id, created_at: datetime()})
                MERGE (j)-[:IMPORTS]->(r)
                MERGE (j)-[:IMPORTS]->(s)
                RETURN j
                """,
                repo_url=repo_url,
                run_id=run_id
            )
            return result.single()["j"]

    def get_all_repositories(self):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (r:Repository)
                RETURN r.name AS name, r.url AS url, r.description AS description
                """
            )
            return [record.data() for record in result]

    def get_all_organizations(self):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (o:Organization)
                RETURN o.name AS name, o.slug AS slug
                """
            )
            return [record.data() for record in result]

    def merge_label(self, repo_url: str, label_name: str):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (r:Repository {url: $url})
                MERGE (l:Label {name: $label})
                MERGE (r)-[:HAS_LABEL]->(l)
                RETURN l
                """,
                url=repo_url,
                label=label_name
            )
            return result.single()["l"]

    def merge_pull_request(self, repo_url: str, number: int, title: str, state: str):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (r:Repository {url: $repo_url})
                MERGE (pr:PullRequest {number: $number})
                ON CREATE SET pr.title = $title, pr.state = $state
                MERGE (r)-[:HAS_PR]->(pr)
                RETURN pr
                """,
                repo_url=repo_url,
                number=number,
                title=title,
                state=state
            )
            return result.single()["pr"]

    def merge_comment(self, pr_number: int, comment_id: int, body: str, author_email: str, ts: float, file_path: str, line_number: int):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (pr:PullRequest {number: $pr_number})
                MATCH (f:File {path: $file_path})
                MERGE (c:Comment {id: $comment_id})
                ON CREATE SET c.body = $body, c.author = $author, c.ts = datetime({epochSeconds: $ts})
                MERGE (pr)-[:HAS_COMMENT]->(c)
                MERGE (c)-[:REFERS_TO {line: $line_number}]->(f)
                RETURN c
                """,
                pr_number=pr_number,
                comment_id=comment_id,
                body=body,
                author=author_email,
                ts=int(ts),
                file_path=file_path,
                line_number=line_number
            )
            return result.single()["c"]

    def merge_source(self, kind: str, url: str):
        with self.driver.session() as session:
            result = session.run(
                """
                MERGE (s:Source {url: $url})
                ON CREATE SET s.kind = $kind
                RETURN s
                """,
                kind=kind,
                url=url
            )
            return result.single()["s"]

    def create_job(self, kind: str, run_id: str):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (s:Source {kind: $kind})
                CREATE (j:Job {run_id: $run_id, created_at: datetime()})
                MERGE (j)-[:IMPORTS]->(s)
                RETURN j
                """,
                kind=kind,
                run_id=run_id
            )
            return result.single()["j"]

    def start_job(self, run_id: str):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (j:Job {run_id: $run_id})
                SET j.started_at = datetime()
                RETURN j
                """,
                run_id=run_id
            )
            return result.single()["j"]

    def complete_job(self, run_id: str):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (j:Job {run_id: $run_id})
                SET j.ended_at = datetime()
                RETURN j
                """,
                run_id=run_id
            )
            return result.single()["j"]

    def get_unstarted_jobs_and_sources(self):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (j:Job)-[:IMPORTS]->(s:Source)
                WHERE NOT EXISTS(j.started_at)
                RETURN j.run_id AS run_id, s.kind AS kind, s.url AS url
                """
            )
            return [record.data() for record in result]




if __name__ == "__main__":
    db = Neo4jDriver()
    # db.clear_database() # TODO make it clear again

    # Example usage: Process a repository
    repo_path = "downloaded_repo"  # Path to the local repository
    repo = Repo(repo_path)

    for commit in repo.iter_commits():
        db.merge_commit(commit)

    db.close()
