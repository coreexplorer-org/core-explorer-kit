#🧰 SETUP INSTRUCTIONS FOR CORE KIT
To get started, clone the necessary repositories in the parent directory.

##📦 Step-by-step
Navigate one directory up from your current location
This ensures you're outside of core kit repo folder:

```bash
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