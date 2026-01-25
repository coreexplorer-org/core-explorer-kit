# 🧰 SETUP INSTRUCTIONS FOR CORE KIT

## About Core Explorer

Core Explorer is a comprehensive development audit and analysis platform designed to systematically review and assess the health of large-scale open source projects, with a primary focus on Bitcoin Core. The platform addresses a critical question in open source development: "Who watches the watcher?" by providing tools to identify when code changes may have received insufficient peer review. At its core, Core Explorer processes git repository data—extracting commit history, tracking authors and committers, analyzing relationships between contributors and their code changes—and stores this information in a [Neo4j graph database](https://neo4j.com/) that models the complex relationships between developers, commits, and code paths. The system includes a [Flask-based backend](backend/) with a [GraphQL API](backend/app/schema.py) for flexible data querying, a [Next.js web interface](CE_demo/README.md) for visualizing repository metrics and contributor activity, and [automated processing pipelines](repo_explorer/README.md) that can analyze entire repositories or drill down into specific files and directories. Key health metrics tracked include self-merge ratios (when authors merge their own code, indicating potential gaps in peer review), contributor acknowledgment patterns, and per-line code quality indices. By providing transparent, data-driven insights into the peer review process, Core Explorer helps maintainers, contributors, and auditors understand the review coverage and quality of code contributions, ultimately strengthening the integrity and security of critical open source projects.

## Data Model

Core Explorer uses a Git-first schema that models repository history as a graph database. The schema is designed around the principle that commits are the primary stable keys (SHA-based), enabling efficient queries about who changed what, when, and how.

### Core Node Types

**Identity** - Represents raw contributor identities from Git
- Properties: `source` (e.g., "git"), `name`, `email` (composite unique key)
- Relationships: `AUTHORED` → Commit, `COMMITTED` → Commit, `TAGGED` → TagObject

**Commit** - Represents Git commits
- Properties: `commit_hash` (unique SHA), `authoredAt`, `committedAt`, `message`, `summary`, `isMerge` (boolean)
- Relationships: `HAS_PARENT` → Commit (with `idx` property for parent order), `HAS_CHANGE` → FileChange, `MERGED_INCLUDES` → Commit (for merge analysis)

**FileChange** - Tracks file-level changes per commit
- Properties: `status` (A/M/D/R for Added/Modified/Deleted/Renamed), `add` (lines added), `del` (lines deleted), `rename_from` (nullable), `isSensitive` (boolean), `commit_hash`, `path` (composite unique key with commit_hash)
- Relationships: `OF_PATH` → Path

**Path** - Represents file paths in the repository
- Properties: `path` (unique string)
- Relationships: Connected via FileChange nodes

**Ref** - Represents Git branches and tags
- Properties: `kind` ("branch" or "tag"), `name`, `remote` (nullable, e.g., "origin")
- Relationships: `POINTS_TO` → Commit or TagObject

**TagObject** - Represents annotated Git tags
- Properties: `name`, `taggerAt` (datetime), `message`
- Relationships: `TAG_OF` → Commit, `HAS_SIGNATURE` → PGPKey

**PGPKey** - Represents PGP/GPG keys used for signing
- Properties: `fingerprint` (unique), `createdAt` (nullable), `revokedAt` (nullable)
- Relationships: Connected via `HAS_SIGNATURE` from Commits and TagObjects

**IngestRun** - Tracks each data import session
- Properties: `id` (unique UUID), `pulledAt` (datetime), `status`, progress counters
- Relationships: `SAW_REF` → RefState

**RefState** - Snapshots of ref positions at import time
- Properties: `name`, `kind`, `remote`, `tipSha` (commit SHA at snapshot time)
- Relationships: `POINTS_TO` → Commit

### Key Relationships

- `AUTHORED` / `COMMITTED`: Links Identity nodes to Commit nodes with timestamp properties
- `HAS_PARENT`: Links commits to their parent commits (enables ancestry traversal)
- `MERGED_INCLUDES`: For merge commits, links to commits introduced by the merge (reachable from 2nd parent but not 1st)
- `HAS_CHANGE`: Links commits to FileChange nodes representing file modifications
- `HAS_SIGNATURE`: Links Commits and TagObjects to PGPKey nodes with validation status
- `SAW_REF`: Links IngestRun to RefState snapshots (enables tracking ref movement over time)

### Data Integrity

The schema enforces uniqueness constraints on:
- `Commit.commit_hash`
- `Identity(source, email, name)`
- `Path.path`
- `Ref(kind, name, remote)`
- `PGPKey.fingerprint`
- `IngestRun.id`
- `FileChange(commit_hash, path)`

These constraints ensure data integrity and enable efficient lookups and merges during incremental imports.

### Query Patterns Enabled

The schema supports powerful analysis queries such as:
- **Self-merge detection**: Find commits where the author and committer are the same
- **Sensitive path analysis**: Track changes to critical code paths (e.g., consensus, policy)
- **Merge ancestry analysis**: Identify which commits were introduced by each merge
- **Temporal ref tracking**: Detect force-pushes and history rewrites by comparing RefState snapshots
- **PGP signature auditing**: Track which commits and tags are signed, and by which keys

## Project Structure

The Core Explorer Kit is organized into several key directories, each serving a specific purpose in the data processing and visualization pipeline. Below is a detailed breakdown of the project structure, including Docker configuration and data dependencies.

```
core-explorer-kit/
│
├── backend/                          # Flask backend service (Docker service: "backend")
│   ├── app/                          # Python application code
│   │   ├── app.py                    # Flask app with REST & GraphQL endpoints
│   │   ├── schema.py                 # GraphQL schema definitions
│   │   ├── git_processor.py          # Git repository processing logic
│   │   ├── neo4j_driver.py           # Neo4j database connection & queries
│   │   ├── commit_details.py         # Commit metadata extraction
│   │   └── config.py                 # Configuration (Neo4j connection, repo paths)
│   ├── Dockerfile                    # Backend container build configuration
│   ├── Pipfile                       # Python dependencies (pipenv)
│   └── wsgi.py                       # WSGI entry point for production
│
├── CE_demo/                          # Next.js frontend application
│   ├── app/                          # Next.js app directory
│   │   ├── api/                      # API route handlers
│   │   ├── page.jsx                  # Main dashboard page
│   │   └── pr/[id]/                  # Pull request detail pages
│   ├── components/                   # React components
│   ├── public/                       # Static assets
│   ├── package.json                  # Node.js dependencies
│   └── README.md                     # Frontend documentation
│
├── repo_explorer/                    # Ruby scripts for data processing
│   ├── github_scrape_commits_or_pulls.rb  # GitHub API scraping
│   ├── process_commit_data.rb        # Commit data processing
│   └── README.md                     # Processing pipeline documentation
│
├── frontend/                         # Static HTML frontend (served by nginx)
│   ├── index.html                    # Landing page
│   ├── project.html                  # Project view page
│   └── profile.html                  # Profile view page
│
├── data/                             # Data persistence directory (⚠️ REQUIRED)
│   ├── neo4j/                        # Neo4j database storage (Docker volume)
│   │   ├── databases/                 # Neo4j database files
│   │   └── transactions/             # Transaction logs
│   │   └── [Persisted in Docker volume: ./data/neo4j:/data]
│   │
│   └── user_supplied_repo/           # Git repository to analyze (⚠️ REQUIRED)
│       └── [Cloned repository, e.g., bitcoin/bitcoin]
│       └── [Mounted to backend as: ./data/user_supplied_repo:/app/bitcoin]
│
├── docker-compose.yml                # Docker orchestration configuration
├── nginx.conf                        # Nginx reverse proxy configuration
└── README.md                         # This file
```

### Docker Services Configuration

The project uses Docker Compose to orchestrate three main services:

1. **neo4j** (Database)
   - **Image**: `neo4j:5.20.0`
   - **Ports**: `7474` (HTTP), `7687` (Bolt protocol)
   - **Volume**: `./data/neo4j:/data` - Persists database files
   - **Health Check**: Waits for Neo4j to be ready before starting dependent services
   - **Dependencies**: None (starts first)

2. **backend** (Flask API)
   - **Build**: `./backend` (uses `backend/Dockerfile`)
   - **Ports**: `5000:5000`
   - **Volumes**: 
     - `./backend/app:/app` - App code for live reloading
     - `${USER_SUPPLIED_REPO_PATH}:/app/bitcoin` - Git repository access (environment-configurable)
   - **Dependencies**: Waits for `neo4j` health check
   - **Network**: Connects to `appnet` to communicate with Neo4j

3. **nginx** (Reverse Proxy)
   - **Image**: `nginx:alpine`
   - **Ports**: `8080:8080`
   - **Volumes**:
     - `./nginx.conf:/etc/nginx/nginx.conf:ro` - Nginx configuration
     - `./frontend:/app/frontend` - Static HTML files
   - **Dependencies**: Waits for `neo4j` and `backend` services
  - **Routing**:
    - `/api/*` → Proxies to `backend:5000`
    - `/` → Serves static files from `/app/frontend`

### Data Dependencies

**Required Data Directories:**

1. **`data/user_supplied_repo/`** (⚠️ REQUIRED)
   - **Purpose**: Contains the git repository to be analyzed
   - **Setup**: Clone your target repository here (e.g., `git clone https://github.com/bitcoin/bitcoin.git user_supplied_repo`)
   - **Docker Mount**: Mounted to backend container at `/app/bitcoin`
   - **Used By**: `backend/app/git_processor.py` reads from `config.CONTAINER_SIDE_REPOSITORY_PATH`

2. **`data/neo4j/`** (Auto-created, but required for persistence)
   - **Purpose**: Stores Neo4j graph database files
   - **Setup**: Created automatically on first run
   - **Docker Mount**: Mounted to Neo4j container at `/data`
   - **Persistence**: Database data persists across container restarts
   - **Note**: Delete this folder to reset the database

**Optional Data:**
- `CE_demo/data/commits.csv` - Sample commit data for frontend development

### Key Configuration Files

- **`.env`**: Environment configuration for sensitive credentials and deployment-specific settings (not committed to git)
  - `APP_NEO4J_USER`: Neo4j database username (default: `neo4j`)
  - `APP_NEO4J_PASSWORD`: Neo4j database password (⚠️ change for production!)
  - `CONTAINER_SIDE_REPOSITORY_PATH`: Path to repository inside container (default: `/app/bitcoin`)
  - `USER_SUPPLIED_REPO_PATH`: Path to repository on host (default: `./data/user_supplied_repo`)
- **`.env.example`**: Template for `.env` file with placeholder values (committed to git)
- **`backend/app/config.py`**: Reads configuration from environment variables with fallback defaults
- **`nginx.conf`**: Routes API requests to backend and serves static frontend files
- **`docker-compose.yml`**: Orchestrates all services and defines network topology

## Local Development Environment

New contributors can stay productive by developing the Python backend locally while still relying on Docker Compose for the stateful services (Neo4j and nginx). The checklist below assumes macOS or Linux, but the same steps work on Windows with WSL2.

### Prerequisites

- Python 3.11 (earlier versions work but match the Docker image for fewer surprises)
- [`pipenv`](https://pipenv.pypa.io/) for dependency + virtualenv management
- Docker Desktop (or Docker Engine) with Compose v2 enabled
- Git, curl, and a modern browser for inspecting GraphQL + Neo4j UIs

### First-time setup

```bash
git clone https://github.com/coreexplorer-org/core-explorer-kit.git
cd core-explorer-kit

# Create environment configuration file
cp .env.example .env
# Edit .env and update APP_NEO4J_PASSWORD and other settings as needed

# Create + populate the data mounts expected by docker-compose.yml
mkdir -p data
cd data
git clone https://github.com/bitcoin/bitcoin.git user_supplied_repo
cd ..

# Install backend dependencies inside a virtual environment
cd backend
pipenv install --dev
```

### Running the stack

1. **Launch the infrastructure:** from the repo root run `docker compose up -d neo4j nginx`. This keeps Neo4j + nginx identical to production while freeing the backend for local iteration. Use `docker compose logs -f neo4j` if you need to confirm readiness.
2. **Enter the backend virtualenv:** `cd backend && pipenv shell`.
3. **Start the Flask server with live reload:** `FLASK_APP=app.app FLASK_RUN_PORT=5000 flask run --debug`. The app will connect to the Neo4j container via the hostname defined in `backend/app/config.py`.
4. **Iterate:** edit files under `backend/app/` and Flask reloads automatically. Hit `http://localhost:5000/api/graphql` (direct) or `http://localhost:8080/api/graphql` (via nginx) to interact with GraphQL.

To stop everything, exit the Pipenv shell and run `docker compose down` from the repository root. If you need to reset Neo4j data, delete the host folder at `./data/neo4j` (bind mount) before starting the stack again.

### Bootstrap scripts

Two bootstrap scripts are provided for automated deployment:

#### `scripts/bootstrap-stack.sh` (Local/Development)

For local development or single-user setups:

```bash
./scripts/bootstrap-stack.sh
```

This script:
- Clones the repository to `~/core-explorer-kit` if not present
- Resets the cloned repo to the newest `origin/main` state (discarding local changes)
- **Checks for `.env` file** and prompts to create it if missing
- Rebuilds the backend Docker image
- Starts Neo4j, backend, and nginx services
- Configures git `safe.directory` for the mounted repository (reads `CONTAINER_SIDE_REPOSITORY_PATH` from `.env`)

#### `scripts/bootstrap-sov-stack.sh` (Production/Server)

For production deployments on dedicated servers:

```bash
./scripts/bootstrap-sov-stack.sh
```

This script:
- Must be run as the `deploy` user (enforces security)
- Clones/updates repository to `/opt/core-explorer-kit`
- Resets the cloned repo to the newest `origin/main` state (discarding local changes)
- **Checks for `.env` file** and prompts to create it if missing
- Links persistent data storage from `/srv/core-explorer-kit/data`
- Pulls pre-built Docker images (no local builds)
- Starts the stack with production-ready configuration
- Configures git `safe.directory` for the mounted repository (reads `CONTAINER_SIDE_REPOSITORY_PATH` from `.env`)

#### Production: safe reset sequence (Neo4j v5 upgrade)

If you are intentionally discarding Neo4j data during a production upgrade, follow this exact sequence to avoid bind-mount confusion:

1. Stop the stack from `/opt/core-explorer-kit`:
   ```bash
   docker compose down
   ```
2. Remove the host data directory (this is the bind mount target):
   ```bash
   rm -rf /srv/core-explorer-kit/data/neo4j
   ```
   If you are running from the repo directory and `./data` is a symlink to `/srv/core-explorer-kit/data`, the equivalent is:
   ```bash
   rm -rf ./data/neo4j
   ```
3. Re-run the production bootstrap:
   ```bash
   ./scripts/bootstrap-sov-stack.sh
   ```

#### Environment Configuration

Both scripts will interactively prompt you to create a `.env` file if one doesn't exist:

```
WARNING: .env file not found

Would you like to create a .env file now? (y/n)
y
Creating .env file...

APP_NEO4J_USER [neo4j]: 
APP_NEO4J_PASSWORD [your_secure_password_here]: my_secure_password
CONTAINER_SIDE_REPOSITORY_PATH [/app/bitcoin]: 
USER_SUPPLIED_REPO_PATH [./data/user_supplied_repo]: 

.env file created successfully!
```

You can accept defaults by pressing Enter, or provide custom values. The `.env` file is automatically ignored by git to protect sensitive credentials.

### Common developer commands

```bash
# Lint + format (if you add tooling later, wire it up here)
pipenv run pytest backend/tests -q          # run fast unit tests
docker compose logs -f backend              # tail backend logs when containerized
docker compose exec backend bash           # hop into the container when debugging
pipenv run flask --app app.app routes      # inspect available Flask routes
```

These commands mirror what CI/CD will do: install dependencies with Pipenv, talk to Dockerized services, and run pytest. Staying close to this flow locally keeps surprises to a minimum.

### Repository Path Configuration

The repository path configuration is a critical aspect of Core Explorer's setup, as it determines where the system looks for the git repository to analyze. Understanding this configuration is essential for both initial setup and troubleshooting.

#### Path Configuration Overview

The repository path is configured through a combination of Docker volume mounts and Python configuration:

1. **Host Directory**: `./data/user_supplied_repo/` (on your local machine)
2. **Container Path**: `/app/bitcoin` (inside the backend Docker container)
3. **Configuration Variable**: `CONTAINER_SIDE_REPOSITORY_PATH = "/app/bitcoin"` in `backend/app/config.py`

#### How the Path Mapping Works

The path mapping is established in `docker-compose.yml`:

```yaml
backend:
  volumes:
    - ./data/user_supplied_repo:/app/bitcoin
```

This Docker volume mount creates a bridge between:
- **Host path**: `./data/user_supplied_repo/` (relative to the `core-explorer-kit` directory)
- **Container path**: `/app/bitcoin` (absolute path inside the container)

When the backend container runs, it sees the cloned repository at `/app/bitcoin`, regardless of what the repository is actually called on the host system.

#### Where the Path is Used

The repository path is referenced in several places:

1. **`backend/app/config.py`** (Line 5):
   ```python
   CONTAINER_SIDE_REPOSITORY_PATH = "/app/bitcoin"  # Where a cloned repo exists
   ```
   This is the primary configuration that all Python code uses.

2. **`backend/app/git_processor.py`** (Line 28):
   ```python
   repo = Repo(config.CONTAINER_SIDE_REPOSITORY_PATH)
   ```
   The git processor uses this path to initialize the GitPython `Repo` object for processing commits.

3. **`backend/app/schema.py`** (Line 144):
   ```python
   repo_path = os.path.join(config.CONTAINER_SIDE_REPOSITORY_PATH, folder)
   gitfame.main(['-t', repo_path, '--format=json', '--show-email'])
   ```
   The GraphQL `fame` resolver uses the configuration variable to construct the repository path dynamically, ensuring consistency across the codebase.

#### Setting Up the Repository Path

**Standard Setup (Bitcoin Core):**

1. Create the data directory structure:
   ```bash
   mkdir -p data
   cd data/
   ```

2. Clone the repository into the expected location:
   ```bash
   git clone https://github.com/bitcoin/bitcoin.git user_supplied_repo
   ```

3. The repository structure should be:
   ```
   data/user_supplied_repo/
   ├── .git/              # Required: Git metadata directory
   └── ... (repository files and directories)
   ```
   
   **Note**: Core Explorer only requires a valid git repository with a `.git` directory. The specific files and structure of the repository are not important - any git repository will work.

4. When Docker starts, this maps to `/app/bitcoin/` inside the container, which matches `config.CONTAINER_SIDE_REPOSITORY_PATH`.

#### Using a Different Repository

If you want to analyze a different repository, you have two options:

**Option 1: Keep the same container path (Recommended)**

1. Clone your repository to `data/user_supplied_repo/`:
   ```bash
   rm -rf data/user_supplied_repo  # Remove old repo if needed
   cd data/
   git clone <your-repo-url> user_supplied_repo
   ```

2. No code changes needed - the Docker mount and `config.py` remain the same.

**Option 2: Change the container path**

If you need to use a different container path:

1. Update `docker-compose.yml`:
   ```yaml
   volumes:
     - ./data/user_supplied_repo:/app/your_repo_name
   ```

2. Update `backend/app/config.py`:
   ```python
   CONTAINER_SIDE_REPOSITORY_PATH = "/app/your_repo_name"
   ```


#### Important Notes

- **Path Consistency**: The path in `config.py` must match the Docker volume mount destination path. If the mount is `:/app/bitcoin`, then `CONTAINER_SIDE_REPOSITORY_PATH` must be `/app/bitcoin`.

- **Working Directory**: The backend container's working directory is `/app` (set in `backend/Dockerfile`). This means:
  - Absolute paths like `/app/bitcoin` work from anywhere
  - Relative paths like `./bitcoin/` work when the working directory is `/app`

- **Repository Requirements**: The repository must be a valid git repository with:
  - A `.git` directory
  - At least one commit
  - Readable by the container user (typically root or the user specified in Dockerfile)

- **Path in GraphQL**: The `fame` resolver in `schema.py` uses `config.CONTAINER_SIDE_REPOSITORY_PATH` to construct paths dynamically, so it automatically adapts to any repository path configuration.

#### Troubleshooting Repository Path Issues

**Error: "fatal: not a git repository"**
- Check that `data/user_supplied_repo/` contains a valid git repository
- Verify the Docker volume mount is working: `docker exec backend ls -la /app/bitcoin`
- Ensure the `.git` directory exists in the mounted location

**Error: "No such file or directory"**
- Verify the path in `config.py` matches the Docker mount destination
- Check that the repository was cloned correctly before starting Docker
- Ensure the volume mount path in `docker-compose.yml` is correct

**Error: "SHA is empty, possible dubious ownership in the repository"**
- Git 2.35+ blocks repositories whose owner differs from the current container user; the backend image now preconfigures `/app/bitcoin` as a safe directory.
- If you pulled the repo before this fix, rebuild the backend image so the setting is baked in:
  ```bash
  docker compose build backend
  docker compose up -d backend
  ```
- For a running container that you do not want to rebuild yet, run the following once to trust the mounted repo:
  ```bash
  docker compose exec backend git config --global --add safe.directory /app/bitcoin
  ```

**GraphQL `fame` query fails**
- Verify that `CONTAINER_SIDE_REPOSITORY_PATH` in `config.py` matches your Docker mount destination
- Check that the folder path parameter is relative to the repository root (e.g., `"src/policy"` not `"/app/bitcoin/src/policy"`)
- Ensure the repository is properly mounted and accessible at the configured path

#### Repository Path in Processing Pipeline

When processing git data:

1. **Initial Import**: `process_git_data()` in `git_processor.py` reads from `config.CONTAINER_SIDE_REPOSITORY_PATH` to get all commits
2. **File-Level Analysis**: `find_relevant_commits()` uses `repo.iter_commits(paths=folder_or_file_path)` where paths are relative to the repository root
3. **GraphQL Queries**: The `fame` resolver constructs paths using `os.path.join(config.CONTAINER_SIDE_REPOSITORY_PATH, folder)` and passes them to `gitfame`, where the folder parameter is relative to the repository root

All paths used in the codebase should be relative to the repository root (e.g., `"src/policy"`, `"src/consensus"`), not absolute container paths.

## Getting Started

To get started, clone the necessary repositories in the parent directory.

## 📦 Step-by-step
Navigate one directory up from your current location
This ensures you're outside of core kit repo folder:

```bash
mkdir data
cd data/
git clone https://github.com/bitcoin/bitcoin.git user_supplied_repo
cd ..
# we are now back at the root
cd ..
# Clone the required repositories in parent folder
git clone https://github.com/coreexplorer-org/repo_explorer.git
git clone https://github.com/coreexplorer-org/repex.git
git clone https://github.com/coreexplorer-org/CE_demo.git
```

### Configure environment variables

Before running the stack, create a `.env` file with your configuration:

```bash
# Copy the example file
cp .env.example .env

# Edit with your preferred editor
nano .env  # or vim, code, etc.
```

**Important**: Update at least the `APP_NEO4J_PASSWORD` for security:

```bash
APP_NEO4J_USER=neo4j
APP_NEO4J_PASSWORD=your_secure_password_here  # ⚠️ Change this!
CONTAINER_SIDE_REPOSITORY_PATH=/app/bitcoin
USER_SUPPLIED_REPO_PATH=./data/user_supplied_repo
```

The `.env` file is automatically ignored by git to protect your credentials.

### Run the full environment with Docker Compose

From inside core-explorer-kit (here), run:

```bash
docker compose up
```


### What happens now?

After running `docker compose up`, Core Explorer starts its services in a specific order. Here's what happens and what you need to do next:

#### Service Startup Sequence

1. **Neo4j Database** starts first
   - Initializes the graph database
   - Creates the `data/neo4j/` directory if it doesn't exist
   - Waits for health check to pass (checks HTTP interface on port 7474)
   - **Access**: Neo4j browser UI available at `http://localhost:7474` (username: `neo4j`, password: `password`)

2. **Backend Service** starts after Neo4j is healthy
   - Flask application starts on port 5000
   - Connects to Neo4j database
   - **Note**: The backend does NOT automatically process git data on startup
   - **Access**: API available at `http://localhost:5000/api/` or via nginx at `http://localhost:8080/api/`

3. **Nginx Reverse Proxy** starts last
   - Routes API requests to the backend
   - Serves static frontend files
   - **Access**: Main entry point at `http://localhost:8080/`

#### First-Time Data Import

**Important**: Core Explorer does not automatically import git data when it starts. You must manually trigger the import process.

**Step 1: Verify Services Are Running**

Check that all services are up:
```bash
docker compose ps
```

You should see all three services (neo4j, backend, nginx) with status "Up".

**Step 2: Trigger Git Data Processing**

Navigate to the processing endpoint in your browser or use curl:

```bash
# Via nginx (recommended)
curl http://localhost:8080/api/process_git_data_to_neo4j/

# Or directly to backend
curl http://localhost:5000/api/process_git_data_to_neo4j/
```

Or open in your browser:
```
http://localhost:8080/api/process_git_data_to_neo4j/
```

**Note:** The processing runs asynchronously in a background thread and returns immediately with a Run ID. You can monitor progress using the status endpoint.

**Step 3: What Happens During Ingestion**

When you trigger the processing endpoint:

1. **Background Execution**: The ingestion starts in a separate thread, returning an immediate **Run ID**.
2. **Schema Setup**: The system creates all required Neo4j constraints and indexes, including uniqueness constraints for commits, identities, paths, refs, PGP keys, ingest runs, and file changes.
3. **Ingest Run Creation**: The system creates an `IngestRun` node with a `STARTED` status to track this import session.
4. **Commit Processing (Backbone)**:
   - Reads commits from the git repository (incrementally processes only new commits if the database already contains data).
   - For each commit, creates/updates:
     - **Identity nodes** for authors and committers (with `source`, `name`, and `email` properties).
     - **Commit nodes** with `commit_hash`, `message`, `summary`, `authoredAt`, `committedAt`, and `isMerge` properties.
     - **Relationships**: `AUTHORED` and `COMMITTED` edges (with timestamp properties), and `HAS_PARENT` edges (with `idx` property for parent order).
   - Processes commits in batches for efficiency.
   - Marks status as `COMMITS_COMPLETE` upon successful backbone sync.
5. **Stage Gate Verification**:
   - The system verifies the integrity of the commit backbone before proceeding.
   - If verification fails (e.g., interrupted run), advanced analysis is skipped to protect data integrity.
6. **Advanced Enrichment** (status transitions to `ENRICHING`):
   - **Refs and Tags**: Creates `Ref` and `TagObject` nodes, and `RefState` snapshots linked to the `IngestRun`.
   - **File Changes**: Tracks additions/deletions/renames for specified paths (defaults to sensitive paths like `src/policy`, `src/consensus`), creating `FileChange` and `Path` nodes with `HAS_CHANGE` and `OF_PATH` relationships.
   - **PGP Signatures**: Extracts GPG signatures from commits and tags, creating `PGPKey` nodes and `HAS_SIGNATURE` relationships with validation status.
   - **Merge Analysis**: Computes `MERGED_INCLUDES` relationships to identify which commits were introduced by each merge commit.
7. **Completion**: The `IngestRun` status is updated to `COMPLETED`.

**Step 4: Monitor Progress**

You can monitor the import progress in two ways:

1. **Status Endpoint**:
   - Visit `http://localhost:8080/api/ingest_status/<run_id>/`
   - Shows real-time status (e.g., `STARTED`, `COMMITS_COMPLETE`, `COMPLETED`) and counters for commits, signatures, and merges.

2. **Backend Logs**:
   - `docker compose logs -f backend`
   - Look for progress messages: `"Updated IngestRun <id> status to COMMITS_COMPLETE"`

**Step 5: Verify Import Success**

Once the status endpoint shows `COMPLETED`, verify the data:

1. **Check Neo4j directly**:
   - Run queries to check node counts:
   ```cypher
   MATCH (i:Identity) RETURN count(i) as identities
   MATCH (c:Commit) RETURN count(c) as commits
   ```

2. **Query via GraphQL** (http://localhost:8080/api/graphql):
   ```graphql
   query {
     identities {
       name
       email
       source
     }
   }
   ```

3. **Check Neo4j directly**:
   ```cypher
   MATCH (i:Identity)-[:AUTHORED]->(c:Commit)
   RETURN i.name, count(c) as commits
   ORDER BY commits DESC
   LIMIT 10
   ```

#### New Features in harden_deploy

The latest version introduces several powerful analysis features:

1. **PGP Signature Extraction**
   - Automatically extracts PGP fingerprints from signed commits and tags.
   - Enables auditing of signed vs. unsigned code in sensitive directories.

2. **Granular File Change Tracking**
   - Tracks additions, deletions, and renames at the file level.
   - Automatically flags changes to `SENSITIVE_PATHS` defined in `file_change_processor.py`.

3. **Merge Ancestry Analysis**
   - Computes exactly which commits are brought in by a merge (reachable from 2nd parent but not 1st).
   - Enables "Self-Merge Detection" to identify when developers merge their own work without sufficient peer review.

4. **Incremental Ingestion**
   - Only processes new commits added since the last run.
   - Efficiently snapshots branch movements over time.

#### Expected Processing Times

- **Small repository** (< 1,000 commits): 1-5 minutes
- **Medium repository** (1,000-10,000 commits): 5-30 minutes
- **Large repository** (10,000+ commits, like Bitcoin Core): 30 minutes - 2+ hours

**Note**: Processing time depends on:
- Number of commits in the repository
- Number of unique authors/committers
- System resources (CPU, memory, disk I/O)

#### Troubleshooting First-Time Setup

**Issue: "fatal: not a git repository"**
- Ensure `data/user_supplied_repo/` contains a valid git repository
- Check that the repository was cloned before starting Docker
- Verify the Docker volume mount: `docker exec backend ls -la /app/bitcoin`

**Issue: Processing endpoint times out (504 error)**
- This is normal for large repositories - the import is still running
- Check backend logs: `docker compose logs -f backend`
- The process continues even if the HTTP request times out
- Wait for the "Processed X commits" message in logs

**Issue: Neo4j connection errors**
- Verify Neo4j is healthy: `docker compose ps`
- Check Neo4j logs: `docker compose logs neo4j`
- Ensure Neo4j health check passed before backend started

**Issue: No data appears in GraphQL queries**
- Verify the import completed successfully (check backend logs)
- Check Neo4j browser to see if nodes exist
- Ensure you're querying the correct GraphQL endpoint

#### Next Steps After Initial Import

Once the initial import is complete:

1. **Explore the GraphQL API**: Visit `http://localhost:8080/api/graphql` for the GraphiQL interface
2. **Query repository data**: Use GraphQL queries to explore identities, commits, and relationships
3. **Access the frontend**: Visit `http://localhost:8080/` to see the web interface
4. **Re-run processing**: Subsequent calls to `/api/process_git_data_to_neo4j/` will process additional file paths (if configured)

The system is now ready to analyze your repository's development history and peer review patterns!

### Running Backend Tests

End-to-end tests now cover the git → Neo4j pipeline using disposable resources. They rely on Docker to launch a temporary Neo4j instance, so ensure Docker Desktop is running before executing them.

1. Install backend dependencies (production + dev):
   ```bash
   cd backend
   pipenv install --dev
   ```
2. Run the pytest suite (spins up a short-lived Neo4j container automatically):
   ```bash
   pipenv run pytest
   ```
The fixture fabricates a small Git repository with multiple authors and merge commits, keeping the suite fast while protecting your real data directories.
