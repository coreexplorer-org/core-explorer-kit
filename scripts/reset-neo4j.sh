#!/usr/bin/env bash
# Completely reset Neo4j data directory to fix config issues
# WARNING: This will delete all Neo4j data!

set -euo pipefail

echo "⚠️  WARNING: This will delete all Neo4j data!"
echo "Press Ctrl+C to cancel, or Enter to continue..."
read -r

echo ""
echo "Stopping containers..."
docker compose down

echo "Removing Neo4j data directory..."
rm -rf data/neo4j

echo "✓ Neo4j data directory removed"
echo ""
echo "You can now run: docker compose up --build"
echo "Neo4j will start with a fresh database."
