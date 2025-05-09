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

class FileDetailRecord(graphene.ObjectType):
    # match (f :FileDetailRecord) return f
    #     {
    #   "identity": 46253,
    #   "labels": [
    #     "FileDetailRecord"
    #   ],
    #   "properties": {
    #     "file_path": "src/policy",
    #     "master_sha_at_collection": "9a05b45da60d214cb1e5a50c3d2293b1defc9bb0",
    #     "json_blob": "{"master_sha_at_collection": "9a05b45da60d214cb1e5a50c3d2293b1defc9bb0", "file_paths": "src/policy", "length_of_unique_authors": 67, "unique_author_names": ["Matthew Zipkin", "Peter Todd", "Kristaps Kaupe", "Wladimir J. van der Laan", "Gregory Maxwell", "CryptAxe", "MeshCollider", "Murch", "Akira Takizawa", "esneider", "Gloria Zhao", "Chris Wheeler", "Greg Sanders", "glozow", "TheCharlatan", "Matthew English", "Matt Whitlock", "Mark Friedenbach", "Gregory Sanders", "Pieter Wuille", "James O'Beirne", "Jonas Schnelli", "Dan Raviv", "Vasil Dimov", "Sebastian Falbesoner", "Jon Atack", "DrahtBot", "W. J. van der Laan", "Ava Chow", "Kiminuo", "Matt Corallo", "BtcDrak", "Sjors Provoost", "Ben Woosley", "MacroFake", "Samuel Dobson", "fanquake", "Jim Posen", "dergoegge", "ismaelsadeeq", "Luke Dashjr", "Anthony Towns", "practicalswift", "Philip Kaufmann", "Ryan Ofsky", "sanket1729", "CAnon", "Marcel Kr\u00fcger", "MarcoFalke", "Carl Dong", "John Newbery", "Johnson Lau", "Brian Deery", "Hennadii Stepanov", "Russell Yanofsky", "Veres Lajos", "Karl-Johan Alm", "Jorge Tim\u00f3n", "stickies-v", "Alex Morcos", "Suhas Daftuar", "Andrew Chow", "isle2983", "Dimitris Tsapakidis", "Antoine Poinsot", "Pavel Jan\u00edk", "marcofleon"], "length_of_all_commits": 467}"
    #   },
    #   "elementId": "4:9870c522-5c84-4950-aa9b-9e8143f7c69c:46253"
    # }
    file_path = graphene.String()
    master_sha_at_collection = graphene.String()
    json_blob = graphene.String()

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

    file_detail_records = graphene.List(FileDetailRecord, description="file_detail_record")

    def file_detail_records(self, info):
        db = Neo4jDriver()
        file_detail_records = db.get_all_file_detail_records()
        db.close()
        return [FileDetailRecord(**file_detail_record) for file_detail_record in file_detail_records]

    file_detail_record = graphene.Field(FileDetailRecord, file_path=graphene.String(required=True))

    def resolve_file_detail_record(self, info, email):
        db = Neo4jDriver()
        data = db.get_file_detail_record_with_commits(email)
        if not data:
            return None

        return FileDetailRecord(
            file_path=data["file_path"],
            master_sha_at_collection=data["master_sha_at_collection"],
            json_blob=data['json_blob']
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

schema = graphene.Schema(query=Query)
