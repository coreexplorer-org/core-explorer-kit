# config.py
NEO4J_URI = "bolt://neo4j:7687"  # Bolt protocol (matches Docker port mapping)
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"  # Matches NEO4J_AUTH in docker-compose.yml
CONTAINER_SIDE_REPOSITORY_PATH = "/app/bitcoin"  # Where a cloned repo exists
