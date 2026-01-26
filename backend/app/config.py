# config.py
import os
import logging

NEO4J_URI = "bolt://neo4j:7687"  # Bolt protocol (matches Docker port mapping)
APP_NEO4J_USER = os.getenv("APP_NEO4J_USER", "neo4j")
APP_NEO4J_PASSWORD = os.getenv("APP_NEO4J_PASSWORD", "password")
CONTAINER_SIDE_REPOSITORY_PATH = os.getenv("CONTAINER_SIDE_REPOSITORY_PATH", "/app/bitcoin")


def setup_logging():
    """
    Configure logging for the application.
    
    Sets up root logger with console handler, configurable log level from
    LOG_LEVEL environment variable (default: INFO). Logs are output to stdout/stderr
    for Docker compatibility.
    
    Suppresses verbose Neo4j notification logs (schema info messages) by setting
    neo4j loggers to WARNING level.
    
    This function is idempotent - calling it multiple times is safe and will not
    duplicate handlers or reconfigure unnecessarily.
    """
    # Guard against double initialization
    root_logger = logging.getLogger()
    if root_logger.handlers:
        # Logging already configured, skip reconfiguration
        return
    
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler()  # Outputs to stdout/stderr
        ]
    )
    
    # Suppress verbose Neo4j notification logs (schema info messages)
    # These are informational messages about indexes/constraints already existing
    logging.getLogger("neo4j").setLevel(logging.WARNING)
    logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)
