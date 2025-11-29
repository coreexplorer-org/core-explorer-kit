# src/git_processor.py
from __future__ import annotations

from typing import Iterable, Sequence

from git import Repo, Commit
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
    co_author_nodes: list[str] = []
    for co_author in co_authors:
        co_author_nodes.append(db.merge_actor(co_author))

    db.merge_commit_step(commit, committer_node, author_node, co_author_nodes)

def process_git_data(
    repo_path: str | None = None,
    neo4j_driver: Neo4jDriver | None = None,
    folder_paths: Sequence[str] | None = None,
    commit_limit: int | None = None,
):
    repo = Repo(repo_path or config.CONTAINER_SIDE_REPOSITORY_PATH)
    db = neo4j_driver or Neo4jDriver()
    should_close_driver = neo4j_driver is None
    status_flag = db.merge_import_status()
    print("Import Process Status Result:", status_flag)

    if not status_flag['git_import_complete']:
        commits = find_commits_in_repo(repo, limit=commit_limit)
        print("Performing initial data import...")
        initial_process_commits_into_db(db, commits)
        db.merge_get_import_status_node()
    else:
        print("Skipping initial data import.")

        default_paths: Sequence[str] = (
            "src/policy",
            "src/consensus",
            "src/rpc/mempool.cpp",
        )
        active_paths = default_paths if folder_paths is None else folder_paths
        for path in active_paths:
            process_path_into_db(repo, db, path)

    if should_close_driver:
        db.close()

    return

def import_bitcoin_path(folder_path, repo_path: str | None = None, neo4j_driver: Neo4jDriver | None = None):
    repo = Repo(repo_path or config.CONTAINER_SIDE_REPOSITORY_PATH)
    db = neo4j_driver or Neo4jDriver()
    process_path_into_db(repo, db, folder_path)
    if neo4j_driver is None:
        db.close()

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


def find_commits_in_repo(repo, limit: int | None = None):
    commits: Iterable[Commit] = repo.iter_commits()
    commits = list(commits)
    # Start with the first commit ever
    commits.reverse()
    if limit is not None:
        commits = commits[:limit]
    return commits

def initial_process_commits_into_db(db: Neo4jDriver, commits):

    for commit in commits:
        process_commit(db, commit)
    print(f"Processed {len(commits)} commits into Neo4j.")

if __name__ == "__main__":
    process_git_data()