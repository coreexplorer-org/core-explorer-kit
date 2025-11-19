import graphene
from graphql import GraphQLError

from neo4j_driver import Neo4jDriver  # make sure this is accessible
import json
import io
import gitfame
from contextlib import redirect_stdout
from git_processor import import_bitcoin_path, find_bitcoin_relevant_commits


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

class RelevantCommits(graphene.ObjectType):
    """Summary metrics for commits relevant to a folder or file path."""
    master_sha_at_collection = graphene.String()
    file_paths = graphene.String()  # raw string or could be List; keeping simple
    length_of_unique_authors = graphene.Int()
    unique_author_names = graphene.List(graphene.String)
    length_of_all_commits = graphene.Int()


class Query(graphene.ObjectType):

    relevant_commits = graphene.Field(
        RelevantCommits,
        folder_or_file_path=graphene.String(required=True),
        description="Return summary statistics for commits touching the given folder or file path",
    )

    def resolve_relevant_commits(self, info, folder_or_file_path):
        """Call the utility that gathers commit relevance metrics for the given path."""
        data = find_bitcoin_relevant_commits(folder_or_file_path)
        if not data:
            return None
        return RelevantCommits(
            master_sha_at_collection=data["master_sha_at_collection"],
            file_paths=data["file_paths"],
            length_of_unique_authors=data["length_of_unique_authors"],
            unique_author_names=data["unique_author_names"],
            length_of_all_commits=data["length_of_all_commits"],
        )


    github_organizations = graphene.List(GithubOrganization, description="List all organizations")

    
    def resolve_organizations(self, info):
        db = Neo4jDriver()
        orgs = db.get_all_github_organizations()
        db.close()
        return [GithubOrganization(**org) for org in orgs]


    github_repositories = graphene.List(GithubRepository, description="List all repositories")


    def resolve_github_repositories(self, info):
        db = Neo4jDriver()
        repos = db.get_all_github_repositories()
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

    def resolve_github_repository(self, info, url):
        db = Neo4jDriver()
        repo = db.get_github_repository_by_url(url)
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

class ImportBitcoinPath(graphene.Mutation):
    """Queue a job to import data from a specific Bitcoin source path."""

    class Arguments:
        path = graphene.String(required=True)

    result = graphene.Boolean()

    def mutate(self, info, path):

        import_bitcoin_path(path)

        return ImportBitcoinPath(result=True)



class Mutation(graphene.ObjectType):
    create_github_organization = CreateGithubOrganization.Field()
    create_github_repository = CreateGithubRepository.Field()
    import_bitcoin_path = ImportBitcoinPath.Field()

schema = graphene.Schema(query=Query, mutation=Mutation)
ma = graphene.Schema(query=Query)
