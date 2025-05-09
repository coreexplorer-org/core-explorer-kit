import graphene
from neo4j_driver import Neo4jDriver  # make sure this is accessible
# Optionally move this to a separate types.py if your project is growing
class ActorType(graphene.ObjectType):
    name = graphene.String()
    email = graphene.String()

class Query(graphene.ObjectType):
    hello = graphene.String(description="A typical hello world")
    all_actors = graphene.List(ActorType, description="List all actors in the graph")

    def resolve_hello(self, info):
        return "Hello from Graphene!"

    def resolve_all_actors(self, info):
        db = Neo4jDriver()
        actors = db.get_all_actors()
        db.close()
        return [ActorType(**actor) for actor in actors]

schema = graphene.Schema(query=Query)
