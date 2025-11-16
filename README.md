#🧰 SETUP INSTRUCTIONS FOR CORE KIT

## About Core Explorer

Core Explorer is a comprehensive development audit and analysis platform designed to systematically review and assess the health of large-scale open source projects, with a primary focus on Bitcoin Core. The platform addresses a critical question in open source development: "Who watches the watcher?" by providing tools to identify when code changes may have received insufficient peer review. At its core, Core Explorer processes git repository data—extracting commit history, tracking authors and committers, analyzing relationships between contributors and their code changes—and stores this information in a [Neo4j graph database](https://neo4j.com/) that models the complex relationships between developers, commits, and code paths. The system includes a [Flask-based backend](backend/) with a [GraphQL API](backend/app/schema.py) for flexible data querying, a [Next.js web interface](CE_demo/README.md) for visualizing repository metrics and contributor activity, and [automated processing pipelines](repo_explorer/README.md) that can analyze entire repositories or drill down into specific files and directories. Key health metrics tracked include self-merge ratios (when authors merge their own code, indicating potential gaps in peer review), contributor acknowledgment patterns, and per-line code quality indices. By providing transparent, data-driven insights into the peer review process, Core Explorer helps maintainers, contributors, and auditors understand the review coverage and quality of code contributions, ultimately strengthening the integrity and security of critical open source projects.

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
   - **Image**: `neo4j:latest`
   - **Ports**: `7474` (HTTP), `7687` (Bolt protocol)
   - **Volume**: `./data/neo4j:/data` - Persists database files
   - **Health Check**: Waits for Neo4j to be ready before starting dependent services
   - **Dependencies**: None (starts first)

2. **backend** (Flask API)
   - **Build**: `./backend` (uses `backend/Dockerfile`)
   - **Ports**: `5000:5000`
   - **Volumes**: 
     - `./data/user_supplied_repo:/app/bitcoin` - Git repository access
   - **Dependencies**: Waits for `neo4j` health check
   - **Network**: Connects to `appnet` to communicate with Neo4j

3. **nginx** (Reverse Proxy)
   - **Image**: `nginx:alpine`
   - **Ports**: `80:80`
   - **Volumes**:
     - `./nginx.conf:/etc/nginx/nginx.conf:ro` - Nginx configuration
     - `./frontend:/app/frontend` - Static HTML files
   - **Dependencies**: Waits for `neo4j` and `backend` services
   - **Routing**:
     - `/api/*` → Proxies to `backend:5000`
     - `/process_git_data_to_neo4j/` → Proxies to `backend:5000`
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

- **`backend/app/config.py`**: Defines Neo4j connection (`bolt://neo4j:7687`) and repository path (`/app/bitcoin`)
- **`nginx.conf`**: Routes API requests to backend and serves static frontend files
- **`docker-compose.yml`**: Orchestrates all services and defines network topology

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

3. **`backend/app/schema.py`** (Line 142):
   ```python
   gitfame.main(['-t', f"./bitcoin/{folder}", '--format=json', '--show-email'])
   ```
   ⚠️ **Note**: The GraphQL `fame` resolver uses a hardcoded path `./bitcoin/` relative to the container's working directory. This assumes the repository is mounted at `/app/bitcoin` and the working directory is `/app`, making the relative path `./bitcoin/` resolve correctly.

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
   ├── .git/
   ├── src/
   ├── CMakeLists.txt
   └── ... (other repository files)
   ```

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

3. Update `backend/app/schema.py` (Line 142) to match:
   ```python
   gitfame.main(['-t', f"./your_repo_name/{folder}", '--format=json', '--show-email'])
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

- **Path in GraphQL**: The `fame` resolver in `schema.py` uses a hardcoded relative path `./bitcoin/`. If you change the repository path, you must also update this hardcoded reference.

#### Troubleshooting Repository Path Issues

**Error: "fatal: not a git repository"**
- Check that `data/user_supplied_repo/` contains a valid git repository
- Verify the Docker volume mount is working: `docker exec backend ls -la /app/bitcoin`
- Ensure the `.git` directory exists in the mounted location

**Error: "No such file or directory"**
- Verify the path in `config.py` matches the Docker mount destination
- Check that the repository was cloned correctly before starting Docker
- Ensure the volume mount path in `docker-compose.yml` is correct

**GraphQL `fame` query fails**
- Check that the hardcoded path in `schema.py` line 142 matches your repository mount point
- Verify the folder path parameter is relative to the repository root (e.g., `"src/policy"` not `"/app/bitcoin/src/policy"`)

#### Repository Path in Processing Pipeline

When processing git data:

1. **Initial Import**: `process_git_data()` in `git_processor.py` reads from `config.CONTAINER_SIDE_REPOSITORY_PATH` to get all commits
2. **File-Level Analysis**: `find_relevant_commits()` uses `repo.iter_commits(paths=folder_or_file_path)` where paths are relative to the repository root
3. **GraphQL Queries**: The `fame` resolver uses `gitfame` with paths relative to the repository root

All paths used in the codebase should be relative to the repository root (e.g., `"src/policy"`, `"src/consensus"`), not absolute container paths.

## Getting Started

To get started, clone the necessary repositories in the parent directory.

##📦 Step-by-step
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

### Run the full environment with Docker Compose
From inside core-explorer-kit (here), run:

```bash
docker compose up
```
