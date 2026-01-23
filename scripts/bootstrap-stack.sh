#!/usr/bin/env bash
set -euo pipefail

# Clone + refresh the repo if needed
REPO_URL="https://github.com/coreexplorer-org/core-explorer-kit.git"
WORKDIR="${HOME}/core-explorer-kit"

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

if [ ! -d "$WORKDIR" ]; then
  git clone "$REPO_URL" "$WORKDIR"
fi

cd "$WORKDIR"

# Make sure the working tree is up to date
git fetch origin
git reset --hard origin/main

# --- Check for .env file ---
if [ ! -f "${WORKDIR}/.env" ]; then
  echo "WARNING: .env file not found in ${WORKDIR}"
  echo ""
  if [ -f "${WORKDIR}/.env.example" ]; then
    echo "Would you like to create a .env file now? (y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
      create_env_file "${WORKDIR}/.env.example" "${WORKDIR}/.env"
    else
      echo "ERROR: .env file is required to run the stack." >&2
      echo "Please create ${WORKDIR}/.env manually or run this script again." >&2
      exit 1
    fi
  else
    echo "ERROR: Neither .env nor .env.example found in ${WORKDIR}" >&2
    exit 1
  fi
fi

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

