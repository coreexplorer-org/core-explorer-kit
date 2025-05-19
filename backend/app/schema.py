import graphene
from neo4j_driver import Neo4jDriver  # make sure this is accessible
import json
import io
import gitfame
from contextlib import redirect_stdout


class FameDetail(graphene.ObjectType):
    email = graphene.String()
    commits = graphene.Int()
    lines = graphene.Int()
    files = graphene.Int()
    commits_percent = graphene.Float()
    lines_percent = graphene.Float()
    files_percent = graphene.Float()

class FameTotal(graphene.ObjectType):
    lines = graphene.Int()
    files = graphene.Int()
    commits = graphene.Int()
    contributors = graphene.List(FameDetail)


class BlameLine(graphene.ObjectType):
    commit = graphene.String()
    author = graphene.String()
    date = graphene.String()
    line = graphene.String()

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

    fame = graphene.Field(
        FameTotal,
        folder=graphene.String(required=True),
        description="Return fame stats where each row starts with email"
    )

    def resolve_fame(self, info, folder):
        buf = io.StringIO()
        with redirect_stdout(buf):
            gitfame.main(['-t', f"./bitcoin/{folder}", '--format=json', '--show-email'])

        buf.seek(0)
        raw = json.loads(buf.read())

        print(len(raw))

        contributors = [
            FameDetail(
                email=row[0],
                commits=row[1],
                lines=row[2],
                files=row[3],
                commits_percent=row[4],
                lines_percent=row[5],
                files_percent=row[6]
            )
            for row in raw["data"]
        ]

        return FameTotal(
            lines=raw["total"]["loc"],
            files=raw["total"]["files"],
            commits=raw["total"]["commits"],
            contributors=contributors
        )


class CreateOrganization(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        slug = graphene.String(required=True)

    organization = graphene.Field(Organization)

    def mutate(self, info, name, slug):
        db = Neo4jDriver()
        org = db.merge_organization(name, slug)
        db.close()
        return CreateOrganization(organization=Organization(name=org["name"], slug=org["slug"]))

class CreateRepository(graphene.Mutation):
    class Arguments:
        org_slug = graphene.String(required=True)
        name = graphene.String(required=True)
        url = graphene.String(required=True)
        description = graphene.String()

    repository = graphene.Field(Repository)

    def mutate(self, info, org_slug, name, url, description=""):
        db = Neo4jDriver()
        repo = db.merge_repository(org_slug, name, url, description)
        db.close()
        return CreateRepository(repository=Repository(name=repo["name"], url=repo["url"], description=repo["description"]))

class CreateJob(graphene.Mutation):
    class Arguments:
        org_slug = graphene.String(required=True)
        repo_url = graphene.String(required=True)
        kind = graphene.String(required=True)

    ok = graphene.Boolean()

    def mutate(self, info, org_slug, repo_url, kind):
        db = Neo4jDriver()
        db.create_job(org_slug, repo_url, kind)
        db.close()
        return CreateJob(ok=True)

class Mutation(graphene.ObjectType):
    create_organization = CreateOrganization.Field()
    create_repository = CreateRepository.Field()
    create_job = CreateJob.Field()

schema = graphene.Schema(query=Query, mutation=Mutation)
