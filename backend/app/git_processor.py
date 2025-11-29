# src/git_processor.py
from git import Repo, Commit, Actor
import config
from neo4j_driver import Neo4jDriver

def merge_parents(db, commit):
    for parent in commit.parents:
        db.process_commit(db, parent)
    

def process_commit(db: Neo4jDriver, commit: Commit):
    # Create the humans
    committer = commit.committer
    author = commit.author
    co_authors = list(commit.co_authors)

    committer_node = db.merge_actor(committer)
    author_node = db.merge_actor(author)
    co_author_nodes = list()
    for co_author in co_authors:
        # breakpoint()

        co_author_nodes.extend(db.merge_actor(co_author))

    db.merge_commit_step(commit, committer_node, author_node, co_author_nodes)

def process_git_data():
    repo = Repo(config.CONTAINER_SIDE_REPOSITORY_PATH)
    db = Neo4jDriver()
    status_flag = db.merge_import_status()
    print("Import Process Status Result:", status_flag)
    # db.clear_database()


    if not status_flag['git_import_complete']:
        commits = find_commits_in_repo(repo)
        print("Performing initial data import...")
        initial_process_commits_into_db(db, commits)
        db.merge_get_import_status_node()
    else:
        print("Skipping initial data import.")
        # TODO: try for file details import
        folder_path = "src/policy"
        # folder_path = "src/policy/ephemeral_policy.cpp"
        process_path_into_db(repo, db, folder_path)
        process_path_into_db(repo, db, 'src/consensus')
        process_path_into_db(repo, db, 'src/rpc/mempool.cpp')
        # breakpoint()

    return

def import_bitcoin_path(folder_path):
    repo = Repo(config.CONTAINER_SIDE_REPOSITORY_PATH)
    db = Neo4jDriver()
    process_path_into_db(repo, db, folder_path)

def process_path_into_db(repo, db:Neo4jDriver, folder_path):
    relevant_data = find_relevant_commits(repo, folder_path)
    db.insert_folder_level_details(relevant_data)


def find_bitcoin_relevant_commits(folder_or_file_path):
    repo = Repo(config.CONTAINER_SIDE_REPOSITORY_PATH)
    return find_relevant_commits(repo, folder_or_file_path)

def find_relevant_commits(repo, folder_or_file_path):
# Get the list of commits for the specific folder path
    commits_for_file = list(repo.iter_commits(all=True, paths=folder_or_file_path))

    # Extract the required information
    commits_info = []
    unique_authors = set()

    for commit in commits_for_file:
        commit_info = {
            'commit_hash': commit.hexsha,
            'author_name': commit.author.name,
            'author_email': commit.author.email,
            'committed_date': commit.committed_datetime
        }
        commits_info.append(commit_info)
        unique_authors.add(commit.author.name)

    # Calculate additional metrics
    unique_author_names = list(unique_authors)
    length_of_unique_authors = len(unique_author_names)
    length_of_all_commits = len(commits_info)
    master_sha_at_collection = repo.heads.master.commit.hexsha
    # breakpoint()

    # Prepare the final result
    result = {
        'master_sha_at_collection': master_sha_at_collection,
        'file_paths': folder_or_file_path,
        # 'commits_info': commits_info,
        'length_of_unique_authors': length_of_unique_authors,
        'unique_author_names': unique_author_names,
        'length_of_all_commits': length_of_all_commits
    }
    return result


def find_commits_in_repo(repo):
    commits = list(repo.iter_commits())
    # Start with the first commit ever
    commits.reverse()
    return commits

def initial_process_commits_into_db(db: Neo4jDriver, commits):

    for commit in commits:
        process_commit(db, commit)
    print(f"Processed {len(commits)} commits into Neo4j.")
    
    db.close()

if __name__ == "__main__":
    process_git_data()