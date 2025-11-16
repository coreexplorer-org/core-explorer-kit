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
   - **Used By**: `backend/app/git_processor.py` reads from `config.LOCAL_REPO_PATH`

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
