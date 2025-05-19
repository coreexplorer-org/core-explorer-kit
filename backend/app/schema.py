import graphene
from graphql import GraphQLError

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

class GithubRepository(graphene.ObjectType):
    name = graphene.String()
    description = graphene.String()
    url = graphene.String()

class GithubOrganization(graphene.ObjectType):
    name = graphene.String()
    slug = graphene.String()

class Commit(graphene.ObjectType):
    commit_hash = graphene.String()
    message = graphene.String()

class Actor(graphene.ObjectType):
    name = graphene.String()
    email = graphene.String()
    authored_commits = graphene.List(Commit)
    committed_commits = graphene.List(Commit)


class Query(graphene.ObjectType):

    github_organizations = graphene.List(GithubOrganization, description="List all organizations")

    
    def resolve_organizations(self, info):
        db = Neo4jDriver()
        orgs = db.get_all_organizations()
        db.close()
        return [GithubOrganization(**org) for org in orgs]


    github_repositories = graphene.List(GithubRepository, description="List all repositories")


    def resolve_github_repositories(self, info):
        db = Neo4jDriver()
        repos = db.get_all_repositories()
        db.close()
        return [GithubRepository(**repo) for repo in repos]


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
    
    github_organization = graphene.Field(GithubOrganization, slug=graphene.String(required=True))
    def resolve_github_organization(self, info, slug):
        db = Neo4jDriver()
        org = db.get_github_organization_by_slug(slug)
        db.close()
        if not org:
            return None
        return GithubOrganization(name=org["name"], slug=org["slug"])


    github_repository = graphene.Field(GithubRepository, url=graphene.String(required=True))

    def resolve_repository(self, info, url):
        db = Neo4jDriver()
        repo = db.get_repository_by_url(url)
        db.close()
        if not repo:
            return None
        return GithubRepository(name=repo["name"], url=repo["url"], description=repo.get("description", ""))


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


class CreateGithubOrganization(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        slug = graphene.String(required=True)

    github_organization = graphene.Field(GithubOrganization)

    def mutate(self, info, name, slug):
        db = Neo4jDriver()
        org = db.merge_github_organization(name, slug)
        db.close()
        return CreateGithubOrganization(github_organization=GithubOrganization(name=org["name"], slug=org["slug"]))

class CreateGithubRepository(graphene.Mutation):
    class Arguments:
        org_slug = graphene.String(required=True)
        name = graphene.String(required=True)
        url = graphene.String(required=True)
        description = graphene.String()

    github_repository = graphene.Field(GithubRepository)

    def mutate(self, info, org_slug, name, url, description=""):
        if not url.startswith(f"https://github.com/{org_slug}/"):
            raise GraphQLError("Must be a github repository URL starting with https")
        db = Neo4jDriver()
        repo = db.merge_github_repository(org_slug, name, url, description)
        db.close()
        return CreateGithubRepository(github_repository=GithubRepository(name=repo["name"], url=repo["url"], description=repo["description"]))

class Mutation(graphene.ObjectType):
    create_github_organization = CreateGithubOrganization.Field()
    create_github_repository = CreateGithubRepository.Field()

schema = graphene.Schema(query=Query, mutation=Mutation)
ma = graphene.Schema(query=Query)
