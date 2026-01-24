# src/git_processor.py
from __future__ import annotations

from typing import Iterable, Sequence, List, Dict, Any, Optional, Set
from datetime import datetime
import uuid

from git import Repo, Commit, TagReference
import config
from neo4j_driver import Neo4jDriver
from commit_details import CommitDetails
from file_change_processor import compute_file_changes, compute_file_changes_for_paths, SENSITIVE_PATHS

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
    use_new_schema: bool = True,
):
    """
    Main entry point for Git data import.
    
    Args:
        repo_path: Path to Git repository
        neo4j_driver: Optional Neo4j driver instance
        folder_paths: Optional list of paths to process file changes for
        commit_limit: Optional limit on number of commits to process
        use_new_schema: Whether to use new schema (Identity, FileChange, etc.)
    """
    repo = Repo(repo_path or config.CONTAINER_SIDE_REPOSITORY_PATH)
    db = neo4j_driver or Neo4jDriver()
    should_close_driver = neo4j_driver is None
    
    try:
        if use_new_schema:
            # Create constraints first
            print("Creating schema constraints...")
            db.create_constraints()
            
            # Create ingest run
            run_id = str(uuid.uuid4())
            pulled_at = datetime.now()
            db.create_ingest_run(run_id, pulled_at)
            print(f"Created IngestRun: {run_id}")
            
            # Process commits
            print("Processing commits...")
            process_commits_new_schema(repo, db, commit_limit=commit_limit)
            
            # Process refs and tags
            print("Processing refs and tags...")
            process_refs_and_tags(repo, db, run_id)
            
            # Process file changes for sensitive paths
            new_schema_default_paths: Sequence[str] = (
                "src/policy",
                "src/consensus",
                "src/rpc/mempool.cpp",
            )
            active_paths = new_schema_default_paths if folder_paths is None else folder_paths
            print(f"Processing file changes for paths: {active_paths}")
            process_file_changes_for_paths(repo, db, active_paths, commit_limit=commit_limit)
            
            # Create Git-native events (scaffolding for future multi-source integration)
            print("Creating Git-native events...")
            create_git_events(repo, db, commit_limit=commit_limit)
        else:
            # Legacy import path
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
    finally:
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
    """Legacy method for processing commits one at a time."""
    for commit in commits:
        process_commit(db, commit)
    print(f"Processed {len(commits)} commits into Neo4j.")


def process_commits_new_schema(repo: Repo, db: Neo4jDriver, commit_limit: Optional[int] = None):
    """
    Process commits using the new schema with batch upserts.
    
    Args:
        repo: Git repository
        db: Neo4j driver
        commit_limit: Optional limit on number of commits
    """
    # Get existing commit hashes to enable incremental import
    with db._driver.session() as session:
        result = session.run("MATCH (c:Commit) RETURN c.commit_hash AS sha")
        existing_shas = {record["sha"] for record in result}
    
    print(f"Found {len(existing_shas)} existing commits in database")
    
    # Find new commits (walk from refs)
    new_commits = []
    refs_to_check = []
    
    # Check remote refs first (origin/master, origin/main, etc.)
    for remote in repo.remotes:
        for ref in remote.refs:
            refs_to_check.append(ref)
    
    # Also check local refs
    for ref in repo.refs:
        if ref not in refs_to_check:
            refs_to_check.append(ref)
    
    # Walk commits from ref tips
    seen_shas = set()
    for ref in refs_to_check:
        try:
            for commit in repo.iter_commits(ref):
                if commit.hexsha in existing_shas:
                    break  # Stop when we hit known commits
                if commit.hexsha not in seen_shas:
                    seen_shas.add(commit.hexsha)
                    new_commits.append(commit)
        except Exception as e:
            print(f"Error processing ref {ref}: {e}")
    
    # If no refs or all commits exist, fall back to iterating all commits
    if not new_commits:
        print("No new commits found from refs, checking all commits...")
        for commit in repo.iter_commits():
            if commit.hexsha not in existing_shas:
                new_commits.append(commit)
            if commit_limit and len(new_commits) >= commit_limit:
                break
    
    if commit_limit:
        new_commits = new_commits[:commit_limit]
    
    print(f"Found {len(new_commits)} new commits to process")
    
    if not new_commits:
        print("No new commits to import")
        return
    
    # Prepare batch rows
    commit_rows = []
    for commit in new_commits:
        details = CommitDetails(commit)
        commit_rows.append({
            "sha": details.commit_hash,
            "message": details.message,
            "summary": details.summary,
            "authoredAt": int(details.authored_date),
            "committedAt": int(details.committed_date),
            "isMerge": details.isMerge,
            "parents": details.parent_shas,
            "author": {
                "source": "git",
                "name": details.author_name,
                "email": details.author_email,
            },
            "committer": {
                "source": "git",
                "name": details.committer_name,
                "email": details.committer_email,
            },
            "coauthors": [
                {"source": "git", "name": co.name, "email": co.email}
                for co in details.co_authors
            ] if details.co_authors else [],
        })
    
    # Batch upsert
    db.batch_upsert_commits(commit_rows)
    print(f"Successfully imported {len(commit_rows)} commits")


def process_file_changes_for_paths(
    repo: Repo,
    db: Neo4jDriver,
    target_paths: Sequence[str],
    commit_limit: Optional[int] = None
):
    """
    Process file changes for specific paths.
    
    Args:
        repo: Git repository
        db: Neo4j driver
        target_paths: List of paths to process
        commit_limit: Optional limit on commits
    """
    # Get commits that touch these paths
    commits_to_process = []
    seen_shas = set()
    
    for path in target_paths:
        try:
            for commit in repo.iter_commits(paths=path):
                if commit.hexsha not in seen_shas:
                    seen_shas.add(commit.hexsha)
                    commits_to_process.append(commit)
                if commit_limit and len(commits_to_process) >= commit_limit:
                    break
            if commit_limit and len(commits_to_process) >= commit_limit:
                break
        except Exception as e:
            print(f"Error processing path {path}: {e}")
    
    if commit_limit:
        commits_to_process = commits_to_process[:commit_limit]
    
    print(f"Processing file changes for {len(commits_to_process)} commits")
    
    # Prepare change rows
    change_rows = []
    sensitive_paths_set = set(SENSITIVE_PATHS)
    
    for commit in commits_to_process:
        changes = compute_file_changes_for_paths(commit, list(target_paths), sensitive_paths_set)
        if changes:
            change_rows.append({
                "sha": commit.hexsha,
                "changes": changes,
            })
    
    if change_rows:
        db.batch_upsert_file_changes(change_rows)
        print(f"Successfully imported file changes for {len(change_rows)} commits")
    else:
        print("No file changes to import")


def process_refs_and_tags(repo: Repo, db: Neo4jDriver, run_id: str):
    """
    Process refs and tags, creating snapshots for the ingest run.
    
    Args:
        repo: Git repository
        db: Neo4j driver
        run_id: IngestRun ID
    """
    refs_data = []
    
    # Process branches
    for ref in repo.refs:
        if ref.name.startswith("refs/heads/"):
            name = ref.name.replace("refs/heads/", "")
            try:
                tip_sha = ref.commit.hexsha
                refs_data.append({
                    "name": name,
                    "kind": "branch",
                    "remote": "",
                    "tipSha": tip_sha,
                })
            except Exception as e:
                print(f"Error processing branch {ref.name}: {e}")
    
    # Process remote branches
    for remote in repo.remotes:
        for ref in remote.refs:
            if ref.name.startswith(f"{remote.name}/"):
                name = ref.name.replace(f"{remote.name}/", "")
                try:
                    tip_sha = ref.commit.hexsha
                    refs_data.append({
                        "name": name,
                        "kind": "branch",
                        "remote": remote.name,
                        "tipSha": tip_sha,
                    })
                except Exception as e:
                    print(f"Error processing remote branch {ref.name}: {e}")
    
    # Process tags
    for tag_ref in repo.tags:
        try:
            if tag_ref.tag is not None:
                # Annotated tag
                tag_obj = tag_ref.tag
                tagger = tag_obj.tagger
                target = tag_obj.object
                if hasattr(target, 'hexsha'):
                    target_sha = target.hexsha
                else:
                    target_sha = str(target)
                
                # Upsert tag object
                db.upsert_tags([{
                    "name": tag_ref.name,
                    "taggerAt": int(tag_obj.tagged_date),
                    "message": tag_obj.message or "",
                    "targetSha": target_sha,
                    "tagger": {
                        "source": "git",
                        "name": tagger.name,
                        "email": tagger.email,
                    },
                }])
            else:
                # Lightweight tag
                tip_sha = tag_ref.commit.hexsha
                refs_data.append({
                    "name": tag_ref.name,
                    "kind": "tag",
                    "remote": "",
                    "tipSha": tip_sha,
                })
        except Exception as e:
            print(f"Error processing tag {tag_ref.name}: {e}")
    
    # Snapshot refs
    if refs_data:
        db.snapshot_refs(run_id, refs_data)
        print(f"Successfully snapshotted {len(refs_data)} refs")


def create_git_events(repo: Repo, db: Neo4jDriver, commit_limit: Optional[int] = None):
    """
    Create Event nodes for Git-native actions (scaffolding for future multi-source integration).
    
    This creates events for commits authored/committed and tags created.
    In the future, PRs, messages, etc. will also create Event nodes.
    
    Args:
        repo: Git repository
        db: Neo4j driver
        commit_limit: Optional limit on commits
    """
    # Create events for commits that are already in the database
    # This is a simple implementation - in production, events would be created during commit import
    with db._driver.session() as session:
        # Check if any Event nodes exist to avoid schema validation warnings
        event_check = session.run("MATCH (e:Event) RETURN count(e) AS event_count LIMIT 1")
        event_count_record = event_check.single()
        has_events = event_count_record and event_count_record["event_count"] > 0
        
        # Create events for authored commits
        if has_events:
            # If events exist, check for matching events
            result = session.run(
                """
                MATCH (i:Identity)-[r:AUTHORED]->(c:Commit)
                WHERE r.at IS NOT NULL
                OPTIONAL MATCH (e:Event)-[about_rel:ABOUT]->(c)
                WITH c, r, e,
                     CASE 
                       WHEN e IS NULL THEN NULL
                       WHEN e.type = 'commit_authored' AND e.source = 'git' THEN e
                       ELSE NULL
                     END AS matching_event
                WHERE matching_event IS NULL
                RETURN c.commit_hash AS sha, r.at AS ts
                ORDER BY r.at DESC
                LIMIT $limit
                """,
                limit=commit_limit or 10000
            )
        else:
            # If no events exist, return all commits without checking for events
            result = session.run(
                """
                MATCH (i:Identity)-[r:AUTHORED]->(c:Commit)
                WHERE r.at IS NOT NULL
                RETURN c.commit_hash AS sha, r.at AS ts
                ORDER BY r.at DESC
                LIMIT $limit
                """,
                limit=commit_limit or 10000
            )
        
        event_count = 0
        batch_events = []
        
        for record in result:
            try:
                # Convert timestamp to datetime
                ts = datetime.fromtimestamp(record["ts"])
                batch_events.append({
                    "type": "commit_authored",
                    "source": "git",
                    "ts": ts,
                    "artifact_type": "Commit",
                    "artifact_id": record["sha"]
                })
                event_count += 1
                
                # Batch insert every 1000 events
                if len(batch_events) >= 1000:
                    db.batch_create_events(batch_events)
                    batch_events = []
            except Exception as e:
                print(f"Error preparing event for commit {record.get('sha', 'unknown')}: {e}")
        
        # Insert remaining events
        if batch_events:
            db.batch_create_events(batch_events)
        
        print(f"Created {event_count} Git-native events")

if __name__ == "__main__":
    process_git_data()