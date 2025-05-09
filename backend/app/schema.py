import graphene
from neo4j_driver import Neo4jDriver  # make sure this is accessible


class Repository(graphene.ObjectType):
    name = graphene.String()
    description = graphene.String()
    url = graphene.String()

class Commit(graphene.ObjectType):
    commit_hash = graphene.String()
    message = graphene.String()

class Actor(graphene.ObjectType):
    name = graphene.String()
    email = graphene.String()
    authored_commits = graphene.List(Commit)
    committed_commits = graphene.List(Commit)


class Query(graphene.ObjectType):
    hello = graphene.String(description="A typical hello world")

    def resolve_hello(self, info):
        return "Hello from Graphene!"

    actors = graphene.List(Actor, description="List all actors in the graph")

    def resolve_actors(self, info):
        db = Neo4jDriver()
        actors = db.get_all_actors()
        db.close()
        return [Actor(**actor) for actor in actors]

    actor = graphene.Field(Actor, email=graphene.String(required=True))

    def resolve_actor(self, info, email):
        db = Neo4jDriver()
        data = db.get_actor_with_commits(email)
        if not data:
            return None
        return Actor(
            name=data["name"],
            email=data["email"],
            authored_commits=[
                Commit(
                    commit_hash=commit.get("commit_hash"),
                    message=commit.get("message")
                ) for commit in data["authored_commits"]
            ],
            committed_commits=[
                Commit(
                    commit_hash=commit.get("commit_hash"),
                    message=commit.get("message")
                ) for commit in data["committed_commits"]
            ]
        )
    repository = graphene.Field(Repository, name=graphene.String(required=True))

    def resolve_repository(self, info, name):
        repositories = {
            "bitcoin": {
                "name": "bitcoin",
                "description": "Bitcoin Core reference implementation",
                "url": "https://github.com/bitcoin/bitcoin.git"
            },
            "bitcoinknots": {
                "name": "bitcoinknots",
                "description": "Bitcoin Knots – a Bitcoin Core derivative",
                "url": "https://github.com/bitcoinknots/bitcoin.git"
            }
        }
        key = name.lower()
        return repositories.get(key)

schema = graphene.Schema(query=Query)
