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

# --- Function to create .env from .env.example ---
create_env_file() {
  local env_example="$1"
  local env_file="$2"
  
  if [ ! -f "${env_example}" ]; then
    echo "ERROR: ${env_example} not found. Cannot create .env file." >&2
    return 1
  fi
  
  echo "Creating .env file..."
  echo ""
  
  > "${env_file}"  # Create empty file
  
  while IFS= read -r line || [ -n "$line" ]; do
    # Skip empty lines and comments, but preserve them in output
    if [[ -z "$line" ]] || [[ "$line" =~ ^[[:space:]]*# ]]; then
      echo "$line" >> "${env_file}"
      continue
    fi
    
    # Extract variable name and default value
    if [[ "$line" =~ ^([A-Z_]+)=(.*)$ ]]; then
      var_name="${BASH_REMATCH[1]}"
      default_value="${BASH_REMATCH[2]}"
      
      # Prompt user for value
      echo -n "${var_name} [${default_value}]: "
      read -r user_input
      
      # Use user input if provided, otherwise use default
      if [ -n "$user_input" ]; then
        echo "${var_name}=${user_input}" >> "${env_file}"
      else
        echo "${var_name}=${default_value}" >> "${env_file}"
      fi
    fi
  done < "${env_example}"
  
  echo ""
  echo ".env file created successfully!"
  echo ""
}

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

# --- Check for .env file ---
if [ ! -f "${CODEDIR}/.env" ]; then
  echo "WARNING: .env file not found in ${CODEDIR}"
  echo ""
  if [ -f "${CODEDIR}/.env.example" ]; then
    echo "Would you like to create a .env file now? (y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
      create_env_file "${CODEDIR}/.env.example" "${CODEDIR}/.env"
    else
      echo "ERROR: .env file is required to run the stack." >&2
      echo "Please create ${CODEDIR}/.env manually or run this script again." >&2
      exit 1
    fi
  else
    echo "ERROR: Neither .env nor .env.example found in ${CODEDIR}" >&2
    exit 1
  fi
fi

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
# Read CONTAINER_SIDE_REPOSITORY_PATH from .env file
if [ -f "${CODEDIR}/.env" ]; then
  TARGET_MOUNT=$(grep "^CONTAINER_SIDE_REPOSITORY_PATH=" "${CODEDIR}/.env" | cut -d'=' -f2 | tr -d '"' | tr -d "'" || echo "/app/bitcoin")
else
  TARGET_MOUNT="/app/bitcoin"  # fallback default
fi
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
