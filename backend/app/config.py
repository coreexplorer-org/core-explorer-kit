# config.py
import os

NEO4J_URI = "bolt://neo4j:7687"  # Bolt protocol (matches Docker port mapping)
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
CONTAINER_SIDE_REPOSITORY_PATH = os.getenv("CONTAINER_SIDE_REPOSITORY_PATH", "/app/bitcoin")
