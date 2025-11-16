#🧰 SETUP INSTRUCTIONS FOR CORE KIT

## About Core Explorer

Core Explorer is a comprehensive development audit and analysis platform designed to systematically review and assess the health of large-scale open source projects, with a primary focus on Bitcoin Core. The platform addresses a critical question in open source development: "Who watches the watcher?" by providing tools to identify when code changes may have received insufficient peer review. At its core, Core Explorer processes git repository data—extracting commit history, tracking authors and committers, analyzing relationships between contributors and their code changes—and stores this information in a [Neo4j graph database](https://neo4j.com/) that models the complex relationships between developers, commits, and code paths. The system includes a [Flask-based backend](backend/) with a [GraphQL API](backend/app/schema.py) for flexible data querying, a [Next.js web interface](CE_demo/README.md) for visualizing repository metrics and contributor activity, and [automated processing pipelines](repo_explorer/README.md) that can analyze entire repositories or drill down into specific files and directories. Key health metrics tracked include self-merge ratios (when authors merge their own code, indicating potential gaps in peer review), contributor acknowledgment patterns, and per-line code quality indices. By providing transparent, data-driven insights into the peer review process, Core Explorer helps maintainers, contributors, and auditors understand the review coverage and quality of code contributions, ultimately strengthening the integrity and security of critical open source projects.

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
