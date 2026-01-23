#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/coreexplorer-org/core-explorer-kit.git"
CODEDIR="/opt/core-explorer-kit"
DATAROOT="/srv/core-explorer-kit/data"

# --- Preconditions / guardrails ---
if [ "$(id -un)" != "deploy" ]; then
  echo "ERROR: run as user 'deploy' (the only user in docker group)." >&2
  exit 1
fi

# --- Ensure persistent dirs exist ---
mkdir -p "${DATAROOT}/neo4j" "${DATAROOT}/user_supplied_repo"

# --- Clone or refresh repo into /opt ---
if [ ! -d "${CODEDIR}/.git" ]; then
  # If /opt/core-explorer-kit exists but isn't a git repo, bail to avoid nuking
  if [ -e "${CODEDIR}" ]; then
    echo "ERROR: ${CODEDIR} exists but is not a git repo. Move it aside and retry." >&2
    exit 1
  fi
  git clone "${REPO_URL}" "${CODEDIR}"
fi

cd "${CODEDIR}"
git fetch origin
git reset --hard origin/main

# --- Ensure ./data points to /srv durable storage (no upstream compose patching) ---
# Replace whatever exists at ./data with a symlink to /srv
if [ -e "${CODEDIR}/data" ] && [ ! -L "${CODEDIR}/data" ]; then
  echo "ERROR: ${CODEDIR}/data exists and is not a symlink. Move it aside and retry." >&2
  exit 1
fi
ln -sfn "${DATAROOT}" "${CODEDIR}/data"

# --- Bring stack up ---
# Prefer pull first; build only if needed
docker compose pull
docker compose up -d neo4j
docker compose up -d backend nginx

# --- Fix git safe.directory for mounted repo inside backend container ---
# This is runtime-scoped; doesn't require rebuilds and survives container restarts if the home dir persists.
# If the backend container runs as root, this sets /root/.gitconfig. If it runs as non-root, it sets that user's ~/.gitconfig.
TARGET_MOUNT="/app/bitcoin"
docker compose exec -T backend sh -lc "git config --global --add safe.directory '${TARGET_MOUNT}' >/dev/null 2>&1 || true"

cat <<'EOF'
Services are now running.

Web:
  - http://localhost:8080/  (or your public domain)
API:
  - http://localhost:8080/api/graphql
Import:
  - http://localhost:8080/process_git_data_to_neo4j/

Neo4j Browser (recommended secure access):
  - Keep Neo4j bound to 127.0.0.1 on the host.
  - Use SSH tunnels:
      ssh -L 7474:127.0.0.1:7474 -L 7687:127.0.0.1:7687 deploy@YOUR_SERVER
    then open:
      http://localhost:7474
EOF
