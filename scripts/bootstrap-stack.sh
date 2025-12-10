#!/usr/bin/env bash
set -euo pipefail

# Clone + refresh the repo if needed
REPO_URL="https://github.com/coreexplorer-org/core-explorer-kit.git"
WORKDIR="${HOME}/core-explorer-kit"

if [ ! -d "$WORKDIR" ]; then
  git clone "$REPO_URL" "$WORKDIR"
fi

cd "$WORKDIR"

# Make sure the working tree is up to date
git fetch origin
git reset --hard origin/main

# Build backend image so the safe.directory config is baked in
docker compose build backend

# Start the stack (Neo4j first, then backend + nginx)
docker compose up -d neo4j
docker compose up -d backend nginx

# Ensure git trusts the mounted repo (even though the image now configures it)
docker compose exec backend git config --global --add safe.directory /app/bitcoin >/dev/null || true

# Show how to access the services
cat <<'EOF'
Services are now running. You can:
  - Visit http://localhost:8080/ (or your public domain) for the frontend.
  - Hit http://localhost:8080/api/graphql for the GraphQL API.
  - Trigger the initial import via http://localhost:8080/process_git_data_to_neo4j/
EOF

