import graphene
from graphql import GraphQLError

from neo4j_driver import Neo4jDriver  # make sure this is accessible
import json
import io
import os
import gitfame
from contextlib import redirect_stdout
import config
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

class Identity(graphene.ObjectType):
    name = graphene.String()
    email = graphene.String()
    source = graphene.String()
    authored_commits = graphene.List(Commit)
    committed_commits = graphene.List(Commit)

# Deprecated: Actor type - use Identity instead
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

class TimeBucket(graphene.ObjectType):
    """Time-bucketed commit count for charting."""
    period = graphene.String()
    count = graphene.Int()
    date = graphene.String()

class ContributorGrowthBucket(graphene.ObjectType):
    """Time-bucketed contributor growth for charting."""
    period = graphene.String()
    newContributors = graphene.Int()
    cumulativeContributors = graphene.Int()
    date = graphene.String()

class RepositoryContributor(graphene.ObjectType):
    """Top contributor to a repository."""
    identity = graphene.Field(Identity)
    commitCount = graphene.Int()

class RepositoryActiveFile(graphene.ObjectType):
    """Most active file in a repository."""
    path = graphene.String()
    commitCount = graphene.Int()
    contributorCount = graphene.Int()

class FileContribution(graphene.ObjectType):
    """File contribution statistics."""
    path = graphene.String()
    linesAdded = graphene.Int()
    linesDeleted = graphene.Int()
    totalChanges = graphene.Int()
    commitCount = graphene.Int()

class IdentityStats(graphene.ObjectType):
    """Statistics for an Identity (contributor)."""
    totalCommits = graphene.Int()
    totalLinesAdded = graphene.Int()
    totalLinesDeleted = graphene.Int()
    filesCreated = graphene.Int()
    firstCommitDate = graphene.String()
    lastCommitDate = graphene.String()
    signedCommits = graphene.Int()
    unsignedCommits = graphene.Int()
    signedPercentage = graphene.Float()

class RepositoryStats(graphene.ObjectType):
    """Statistics for a repository."""
    totalCommits = graphene.Int()
    totalFiles = graphene.Int()
    totalLinesOfCode = graphene.Int()
    totalContributors = graphene.Int()
    firstCommitDate = graphene.String()
    lastCommitDate = graphene.String()
    signedCommits = graphene.Int()
    unsignedCommits = graphene.Int()
    signedPercentage = graphene.Float()

class RepositoryHealthMetrics(graphene.ObjectType):
    """Health metrics for a repository."""
    averageCommitsPerContributor = graphene.Float()
    averageTimeBetweenCommits = graphene.Float()  # in seconds
    mostActivePeriod = graphene.String()
    mostActivePeriodCommits = graphene.Int()

class PGPSignatureStats(graphene.ObjectType):
    """PGP signature statistics."""
    uniqueKeys = graphene.Int()

class TopSigner(graphene.ObjectType):
    """Top signer by signed commit count."""
    identity = graphene.Field(Identity)
    signedCommitCount = graphene.Int()

class SignatureAdoptionBucket(graphene.ObjectType):
    """Time-bucketed signature adoption data."""
    period = graphene.String()
    totalCommits = graphene.Int()
    signedCommits = graphene.Int()
    signedPercentage = graphene.Float()
    date = graphene.String()

class FileStats(graphene.ObjectType):
    """Statistics for a file."""
    totalCommits = graphene.Int()
    totalContributors = graphene.Int()
    firstCommitDate = graphene.String()
    lastCommitDate = graphene.String()
    totalLinesAdded = graphene.Int()
    totalLinesDeleted = graphene.Int()

class FileContributor(graphene.ObjectType):
    """Contributor to a file."""
    identity = graphene.Field(Identity)
    commitCount = graphene.Int()
    linesAdded = graphene.Int()
    linesDeleted = graphene.Int()


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

    # Deprecated: Use identities instead
    actors = graphene.List(Actor, description="List all actors in the graph (deprecated - use identities)")

    def resolve_actors(self, info):
        db = Neo4jDriver()
        actors = db.get_all_actors()
        db.close()
        return [Actor(**actor) for actor in actors]

    # Deprecated: Use identity instead
    actor = graphene.Field(Actor, email=graphene.String(required=True), description="Get actor by email (deprecated - use identity)")

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

    # New Identity-based queries
    identities = graphene.List(Identity, description="List all identities in the graph")

    def resolve_identities(self, info):
        db = Neo4jDriver()
        identities = db.get_all_identities()
        db.close()
        return [Identity(**identity) for identity in identities]

    identity = graphene.Field(Identity, email=graphene.String(required=True), source=graphene.String(default_value="git"), description="Get identity by email and source")

    def resolve_identity(self, info, email, source="git"):
        db = Neo4jDriver()
        data = db.get_identity_with_commits(email, source)
        if not data:
            return None
        return Identity(
            name=data["name"],
            email=data["email"],
            source=data.get("source", "git"),
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

    identityStats = graphene.Field(IdentityStats, email=graphene.String(required=True), source=graphene.String(default_value="git"), description="Get statistics for an identity")

    def resolve_identityStats(self, info, email, source="git"):
        db = Neo4jDriver()
        stats = db.get_identity_stats(email, source)
        db.close()
        if not stats:
            return None
        return IdentityStats(**stats)

    identityCommitsOverTime = graphene.List(TimeBucket, email=graphene.String(required=True), source=graphene.String(default_value="git"), timeBucket=graphene.String(default_value="month"), description="Get commits over time for an identity")

    def resolve_identityCommitsOverTime(self, info, email, source="git", timeBucket="month"):
        db = Neo4jDriver()
        buckets = db.get_identity_commits_over_time(email, source, timeBucket)
        db.close()
        return [TimeBucket(**bucket) for bucket in buckets]

    identityTopFiles = graphene.List(FileContribution, email=graphene.String(required=True), source=graphene.String(default_value="git"), limit=graphene.Int(default_value=10), description="Get top files contributed to by an identity")

    def resolve_identityTopFiles(self, info, email, source="git", limit=10):
        db = Neo4jDriver()
        files = db.get_identity_top_files(email, source, limit)
        db.close()
        return [FileContribution(**file) for file in files]

    repositoryStats = graphene.Field(RepositoryStats, repositoryUrl=graphene.String(), description="Get statistics for a repository")

    def resolve_repositoryStats(self, info, repositoryUrl=None):
        db = Neo4jDriver()
        stats = db.get_repository_stats(repositoryUrl)
        db.close()
        if not stats:
            return None
        return RepositoryStats(**stats)

    repositoryCommitsOverTime = graphene.List(TimeBucket, repositoryUrl=graphene.String(), timeBucket=graphene.String(default_value="month"), description="Get commits over time for a repository")

    def resolve_repositoryCommitsOverTime(self, info, repositoryUrl=None, timeBucket="month"):
        db = Neo4jDriver()
        buckets = db.get_repository_commits_over_time(repositoryUrl, timeBucket)
        db.close()
        return [TimeBucket(**bucket) for bucket in buckets]

    fileStats = graphene.Field(FileStats, filePath=graphene.String(required=True), description="Get statistics for a file")

    def resolve_fileStats(self, info, filePath):
        db = Neo4jDriver()
        stats = db.get_file_stats(filePath)
        db.close()
        if not stats:
            return None
        return FileStats(**stats)

    fileCommitsOverTime = graphene.List(TimeBucket, filePath=graphene.String(required=True), timeBucket=graphene.String(default_value="month"), description="Get commits over time for a file")

    def resolve_fileCommitsOverTime(self, info, filePath, timeBucket="month"):
        db = Neo4jDriver()
        buckets = db.get_file_commits_over_time(filePath, timeBucket)
        db.close()
        return [TimeBucket(**bucket) for bucket in buckets]

    fileContributors = graphene.List(FileContributor, filePath=graphene.String(required=True), limit=graphene.Int(default_value=10), description="Get top contributors to a file")

    def resolve_fileContributors(self, info, filePath, limit=10):
        db = Neo4jDriver()
        contributors = db.get_file_contributors(filePath, limit)
        db.close()
        result = []
        for contrib in contributors:
            identity_data = contrib.get("identity", {})
            identity = Identity(
                name=identity_data.get("name", ""),
                email=identity_data.get("email", ""),
                source=identity_data.get("source", "git")
            )
            result.append(FileContributor(
                identity=identity,
                commitCount=contrib.get("commitCount", 0),
                linesAdded=contrib.get("linesAdded", 0),
                linesDeleted=contrib.get("linesDeleted", 0)
            ))
        return result

    allFilePaths = graphene.List(graphene.String, limit=graphene.Int(), description="Get all file paths available in the database")

    def resolve_allFilePaths(self, info, limit=None):
        db = Neo4jDriver()
        paths = db.get_all_file_paths(limit)
        db.close()
        return paths

    allIdentityEmails = graphene.List(graphene.String, limit=graphene.Int(), description="Get all identity emails available in the database")

    def resolve_allIdentityEmails(self, info, limit=None):
        db = Neo4jDriver()
        emails = db.get_all_identity_emails(limit)
        db.close()
        return emails

    repositoryTopContributors = graphene.List(RepositoryContributor, limit=graphene.Int(default_value=10), description="Get top contributors by commit count for the repository")

    def resolve_repositoryTopContributors(self, info, limit=10):
        db = Neo4jDriver()
        contributors = db.get_repository_top_contributors(limit)
        db.close()
        result = []
        for contrib in contributors:
            identity_data = contrib.get("identity", {})
            identity = Identity(
                name=identity_data.get("name", ""),
                email=identity_data.get("email", ""),
                source=identity_data.get("source", "git")
            )
            result.append(RepositoryContributor(
                identity=identity,
                commitCount=contrib.get("commitCount", 0)
            ))
        return result

    repositoryMostActiveFiles = graphene.List(RepositoryActiveFile, limit=graphene.Int(default_value=10), description="Get most active files by commit count for the repository")

    def resolve_repositoryMostActiveFiles(self, info, limit=10):
        db = Neo4jDriver()
        files = db.get_repository_most_active_files(limit)
        db.close()
        return [RepositoryActiveFile(**file) for file in files]

    repositoryContributorGrowth = graphene.List(ContributorGrowthBucket, timeBucket=graphene.String(default_value="month"), description="Get contributor growth over time for the repository")

    def resolve_repositoryContributorGrowth(self, info, timeBucket="month"):
        db = Neo4jDriver()
        buckets = db.get_repository_contributor_growth(timeBucket)
        db.close()
        return [ContributorGrowthBucket(**bucket) for bucket in buckets]

    repositoryHealthMetrics = graphene.Field(RepositoryHealthMetrics, description="Get repository health metrics")

    def resolve_repositoryHealthMetrics(self, info):
        db = Neo4jDriver()
        metrics = db.get_repository_health_metrics()
        db.close()
        if not metrics:
            return None
        return RepositoryHealthMetrics(**metrics)

    pgpSignatureStats = graphene.Field(PGPSignatureStats, description="Get PGP signature statistics")

    def resolve_pgpSignatureStats(self, info):
        db = Neo4jDriver()
        stats = db.get_pgp_signature_stats()
        db.close()
        if not stats:
            return None
        return PGPSignatureStats(**stats)

    repositoryTopSigners = graphene.List(TopSigner, limit=graphene.Int(default_value=10), description="Get top signers by signed commit count")

    def resolve_repositoryTopSigners(self, info, limit=10):
        db = Neo4jDriver()
        signers = db.get_repository_top_signers(limit)
        db.close()
        result = []
        for signer in signers:
            identity_data = signer.get("identity", {})
            identity = Identity(
                name=identity_data.get("name", ""),
                email=identity_data.get("email", ""),
                source=identity_data.get("source", "git")
            )
            result.append(TopSigner(
                identity=identity,
                signedCommitCount=signer.get("signedCommitCount", 0)
            ))
        return result

    repositorySignatureAdoptionTrend = graphene.List(SignatureAdoptionBucket, timeBucket=graphene.String(default_value="month"), description="Get signature adoption trend over time")

    def resolve_repositorySignatureAdoptionTrend(self, info, timeBucket="month"):
        db = Neo4jDriver()
        buckets = db.get_repository_signature_adoption_trend(timeBucket)
        db.close()
        return [SignatureAdoptionBucket(**bucket) for bucket in buckets]
    
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
            repo_path = os.path.join(config.CONTAINER_SIDE_REPOSITORY_PATH, folder)
            gitfame.main(['-t', repo_path, '--format=json', '--show-email'])

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
