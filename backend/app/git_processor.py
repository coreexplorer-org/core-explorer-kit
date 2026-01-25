# src/git_processor.py
from __future__ import annotations

from typing import Iterable, Sequence, List, Dict, Any, Optional, Set
from datetime import datetime
import uuid
import json

from git import Repo, Commit, TagReference
import config
from neo4j_driver import Neo4jDriver
from commit_details import CommitDetails
from file_change_processor import compute_file_changes, compute_file_changes_for_paths, SENSITIVE_PATHS
from signature_extractor import extract_commit_signature, extract_tag_signature
from merge_analyzer import compute_merged_commits

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
    run_id: str | None = None,
):
    """
    Main entry point for Git data import.
    
    Args:
        repo_path: Path to Git repository
        neo4j_driver: Optional Neo4j driver instance
        folder_paths: Optional list of paths to process file changes for
        commit_limit: Optional limit on number of commits to process
        use_new_schema: Whether to use new schema (Identity, FileChange, etc.) [DEPRECATED: defaults to True]
        run_id: Optional existing IngestRun ID to use
    """
    repo = Repo(repo_path or config.CONTAINER_SIDE_REPOSITORY_PATH)
    db = neo4j_driver or Neo4jDriver()
    should_close_driver = neo4j_driver is None
    
    try:
        if use_new_schema:
            # Create constraints first
            print("Creating schema constraints...")
            db.create_constraints()
            
            # Create or use existing ingest run
            run_id = run_id or str(uuid.uuid4())
            pulled_at = datetime.now()
            db.create_ingest_run(run_id, pulled_at)
            print(f"IngestRun: {run_id}")
            
            # 1. PROCESS COMMITS (BACKBONE)
            print("Processing commits...")
            commit_count = process_commits_new_schema(repo, db, commit_limit=commit_limit)
            
            # Mark backbone as complete
            db.update_ingest_run_status(run_id, 'COMMITS_COMPLETE', total_commits=commit_count)
            
            # --- STAGE GATE ---
            run_info = db.get_ingest_run_status(run_id)
            if not run_info or run_info.get('status') != 'COMMITS_COMPLETE':
                print(f"Commit backbone verification failed for {run_id}. Skipping advanced analysis.")
                return
            
            print("Commit backbone verified. Proceeding with advanced enrichment.")
            
            # 2. ENRICHMENT STAGES
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
            
            # Create Git-native events
            print("Creating Git-native events...")
            create_git_events(repo, db, commit_limit=commit_limit)
            
            # Process PGP signatures for commits
            print("Processing PGP signatures for commits...")
            sig_count = process_commit_signatures(repo, db, commit_limit=commit_limit)
            db.update_ingest_run_status(run_id, 'COMMITS_COMPLETE', totalSignaturesProcessed=sig_count)
            
            # Process PGP signatures for tags
            print("Processing PGP signatures for tags...")
            process_tag_signatures(repo, db)
            
            # Process MERGED_INCLUDES for merge commits
            print("Computing MERGED_INCLUDES relationships...")
            merge_count = process_merged_includes(repo, db, merge_limit=None)
            db.update_ingest_run_status(run_id, 'COMMITS_COMPLETE', totalMergesProcessed=merge_count)
            
            # Mark run as fully complete
            db.update_ingest_run_status(run_id, 'COMPLETED')
            print(f"IngestRun {run_id} successfully completed.")
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


def process_commits_new_schema(repo: Repo, db: Neo4jDriver, commit_limit: Optional[int] = None) -> int:
    """
    Process commits using the new schema with batch upserts.
    
    Returns:
        int: Number of commits processed
    """
    # Get existing commit hashes to enable incremental import
    with db._driver.session() as session:
        result = session.run("MATCH (c:Commit) RETURN c.commit_hash AS sha")
        existing_shas = {record["sha"] for record in result}
    
    print(f"Found {len(existing_shas)} existing commits in database")
    
    # Find new commits (walk from refs)
    new_commits = []
    refs_to_check = []
    
    for remote in repo.remotes:
        for ref in remote.refs:
            refs_to_check.append(ref)
    
    for ref in repo.refs:
        if ref not in refs_to_check:
            refs_to_check.append(ref)
    
    seen_shas = set()
    for ref in refs_to_check:
        try:
            for commit in repo.iter_commits(ref):
                if commit.hexsha in existing_shas:
                    break
                if commit.hexsha not in seen_shas:
                    seen_shas.add(commit.hexsha)
                    new_commits.append(commit)
        except Exception as e:
            print(f"Error processing ref {ref}: {e}")
    
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
        return 0
    
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
    return len(commit_rows)


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


def process_commit_signatures(
    repo: Repo, 
    db: Neo4jDriver, 
    commit_limit: Optional[int] = None
) -> int:
    """
    Extract and store PGP signatures for commits already in the database.
    
    Returns:
        int: Number of signatures found and stored
    """
    BATCH_SIZE = 100
    
    # Query database for commits that don't have signatures yet
    with db._driver.session() as session:
        # Get total commit count
        total_commits_result = session.run("MATCH (c:Commit) RETURN count(c) AS count")
        total_commits_record = total_commits_result.single()
        total_commits = total_commits_record["count"] if total_commits_record else 0
        
        # Count commits with signatures (may produce warnings if relationship type doesn't exist yet, but query still works)
        commits_with_sigs_result = session.run("MATCH (c:Commit)-[:HAS_SIGNATURE]->(:PGPKey) RETURN count(DISTINCT c) AS count")
        commits_with_sigs_record = commits_with_sigs_result.single()
        commits_with_sigs = commits_with_sigs_record["count"] if commits_with_sigs_record else 0
        
        # Count commits already checked for signatures
        checked_commits_result = session.run("MATCH (c:Commit) WHERE c.signature_checked = true RETURN count(c) AS count")
        checked_commits_record = checked_commits_result.single()
        checked_commits = checked_commits_record["count"] if checked_commits_record else 0
        
        if commit_limit:
            query = """
            MATCH (c:Commit)
            WHERE (c.signature_checked IS NULL OR c.signature_checked = false)
            AND NOT (c)-[:HAS_SIGNATURE]->(:PGPKey)
            RETURN c.commit_hash AS sha
            ORDER BY c.committedAt DESC
            LIMIT $limit
            """
            result = session.run(query, limit=commit_limit)
        else:
            query = """
            MATCH (c:Commit)
            WHERE (c.signature_checked IS NULL OR c.signature_checked = false)
            AND NOT (c)-[:HAS_SIGNATURE]->(:PGPKey)
            RETURN c.commit_hash AS sha
            """
            result = session.run(query)
        
        commit_shas = [record["sha"] for record in result]
    
    if not commit_shas:
        print("No commits without signatures found")
        return
    
    commits_without_sigs = total_commits - commits_with_sigs
    print(f"Signature processing status: {total_commits} total commits, {checked_commits} already checked (skipped), {commits_with_sigs} have signatures, {len(commit_shas)} need processing")
    print(f"Processing signatures for {len(commit_shas)} commits")
    
    # Diagnostic: Test a few commits to see what git actually outputs
    print("Testing signature extraction on sample commits...")
    sample_commits = commit_shas[:10]
    for test_sha in sample_commits:
        try:
            import subprocess
            test_commit = repo.commit(test_sha)
            git_result = subprocess.run(
                ['git', 'show', '--show-signature', test_sha],
                cwd=repo.working_dir or repo.git_dir,
                capture_output=True,
                text=True,
                timeout=10
            )
            # Check both stdout and stderr
            combined_output = (git_result.stdout or '') + '\n' + (git_result.stderr or '')
            has_sig_markers = any(marker in combined_output.lower() for marker in ['gpg', 'signature', 'fingerprint', 'key id'])
            
            extracted = extract_commit_signature(test_commit)
            if extracted and extracted.get('fingerprint'):
                print(f"  ✓ {test_sha[:8]}: Found signature {extracted['fingerprint'][:16]}...")
            elif has_sig_markers:
                print(f"  ⚠ {test_sha[:8]}: Git output has signature markers but extraction failed")
                # Show a snippet
                sig_lines = [l for l in combined_output.split('\n') if any(m in l.lower() for m in ['gpg', 'signature', 'fingerprint'])][:3]
                if sig_lines:
                    print(f"    Sample: {sig_lines[0][:80]}")
            else:
                # Only show first 2 to avoid spam
                if test_sha == sample_commits[0]:
                    print(f"  - {test_sha[:8]}: No signature indicators in git output")
        except Exception as e:
            if test_sha == sample_commits[0]:
                print(f"  ✗ {test_sha[:8]}: Error - {e}")
    
    # Check current database state
    with db._driver.session() as session:
        existing_keys_record = session.run("MATCH (k:PGPKey) RETURN count(k) AS count").single()
        existing_keys = existing_keys_record["count"] if existing_keys_record else 0
        
        existing_sigs_record = session.run("MATCH ()-[r:HAS_SIGNATURE]->() RETURN count(r) AS count").single()
        existing_sigs = existing_sigs_record["count"] if existing_sigs_record else 0
        
        # Check what has signatures (commits vs tags)
        commit_sigs_record = session.run("MATCH (c:Commit)-[:HAS_SIGNATURE]->() RETURN count(DISTINCT c) AS count").single()
        commit_sigs = commit_sigs_record["count"] if commit_sigs_record else 0
        
        tag_sigs_record = session.run("MATCH (t:TagObject)-[:HAS_SIGNATURE]->() RETURN count(DISTINCT t) AS count").single()
        tag_sigs = tag_sigs_record["count"] if tag_sigs_record else 0
        
        print(f"Database state: {existing_sigs} signatures ({commit_sigs} commits, {tag_sigs} tags), {existing_keys} PGP keys")
    
    # Extract signatures and collect data in batches
    key_rows = []
    signature_rows = []
    seen_fingerprints = set()
    
    # Track statistics across batches
    total_signed = 0
    total_unsigned = 0
    
    # Track sample fingerprints for diagnostics
    sample_fingerprints = []
    
    # Track errors for debugging
    error_count = 0
    sample_errors = []  # Keep first few errors for debugging
    
    # Track processed commits to mark as checked (both signed and unsigned)
    processed_commits = []
    
    for i, sha in enumerate(commit_shas, 1):
        try:
            commit = repo.commit(sha)
            sig_data = extract_commit_signature(commit)
            
            # Track this commit as processed (will be marked as checked)
            processed_commits.append(sha)
            
            if sig_data and sig_data.get('fingerprint'):
                fingerprint = sig_data['fingerprint']
                
                # Validate fingerprint format (should be 40 hex chars)
                if len(fingerprint) != 40 or not all(c in '0123456789ABCDEF' for c in fingerprint):
                    # Skip invalid fingerprints (likely false positives from parsing)
                    if i <= 10:  # Only log first few
                        print(f"  Warning: Invalid fingerprint format for commit {sha[:8]}: {fingerprint[:20]}...")
                    total_unsigned += 1
                    continue
                
                # Collect unique PGP keys
                if fingerprint not in seen_fingerprints:
                    key_rows.append({
                        'fingerprint': fingerprint,
                        'createdAt': None,  # Can be populated later
                        'revokedAt': None
                    })
                    seen_fingerprints.add(fingerprint)
                
                # Collect signature relationships
                signature_rows.append({
                    'artifact_type': 'Commit',
                    'artifact_id': sha,
                    'fingerprint': fingerprint,
                    'valid': sig_data.get('valid'),
                    'method': sig_data.get('method', 'gpg')
                })
                total_signed += 1
            else:
                total_unsigned += 1
        except Exception as e:
            error_count += 1
            if len(sample_errors) < 5:
                sample_errors.append(f"{sha[:8]}: {str(e)}")
            if error_count <= 10 or error_count % 1000 == 0:
                print(f"Error processing signature for commit {sha[:8]}: {e}")
            total_unsigned += 1
            # Still mark as processed even if there was an error
            processed_commits.append(sha)
            continue
        
        # Save batch every BATCH_SIZE commits
        if i % BATCH_SIZE == 0:
            # Save keys first
            if key_rows:
                db.batch_upsert_pgp_keys(key_rows)
                key_rows = []  # Clear after saving
            
            # Save signatures
            if signature_rows:
                db.batch_create_signatures(signature_rows)
                signature_rows = []  # Clear after saving
            
            # Mark all processed commits in this batch as checked
            if processed_commits:
                db.batch_mark_commits_checked_for_signatures(processed_commits)
                processed_commits = []  # Clear after marking
            
            # Verify database state after batch save
            with db._driver.session() as session:
                # Count total PGP keys in DB
                key_count_result = session.run("MATCH (k:PGPKey) RETURN count(k) AS count")
                key_count_record = key_count_result.single()
                key_count = key_count_record["count"] if key_count_record else 0
                
                # Count total signature relationships in DB
                sig_count_result = session.run("MATCH ()-[r:HAS_SIGNATURE]->() RETURN count(r) AS count")
                sig_count_record = sig_count_result.single()
                sig_count = sig_count_record["count"] if sig_count_record else 0
                
                # Calculate key reuse ratio (signatures per key)
                ratio = sig_count / key_count if key_count > 0 else 0
                print(f"Processed {i}/{len(commit_shas)} commits... (found {total_signed} signed, {total_unsigned} unsigned so far) [DB: {sig_count} signatures, {key_count} keys, {ratio:.1f} sigs/key]")
                
                # Show sample fingerprints on first batch
                if i == BATCH_SIZE and sample_fingerprints:
                    print(f"  Sample fingerprints found: {', '.join([f'{sha}:{fp[:16]}...' for sha, fp in sample_fingerprints])}")
    
    # Save remaining data (final batch)
    if key_rows:
        db.batch_upsert_pgp_keys(key_rows)
        print(f"Upserted {len(key_rows)} PGP keys")
    
    if signature_rows:
        db.batch_create_signatures(signature_rows)
        print(f"Created {len(signature_rows)} signature relationships")
    
    # Mark all remaining processed commits as checked
    if processed_commits:
        db.batch_mark_commits_checked_for_signatures(processed_commits)
        print(f"Marked {len(processed_commits)} commits as checked for signatures")
    
    # Verify final database state
    with db._driver.session() as session:
        # Count total PGP keys in DB
        key_count_result = session.run("MATCH (k:PGPKey) RETURN count(k) AS count")
        key_count_record = key_count_result.single()
        total_keys_in_db = key_count_record["count"] if key_count_record else 0
        
        # Count total signature relationships in DB
        sig_count_result = session.run("MATCH ()-[r:HAS_SIGNATURE]->() RETURN count(r) AS count")
        sig_count_record = sig_count_result.single()
        total_sigs_in_db = sig_count_record["count"] if sig_count_record else 0
        
        # Count commits with signatures
        commit_sig_count_result = session.run("MATCH (c:Commit)-[:HAS_SIGNATURE]->() RETURN count(DISTINCT c) AS count")
        commit_sig_count_record = commit_sig_count_result.single()
        commits_with_sigs = commit_sig_count_record["count"] if commit_sig_count_record else 0
    
    # Print final summary
    print(f"Completed: processed {len(commit_shas)} commits, found {total_signed} signed, {total_unsigned} unsigned")
    print(f"Database state: {total_sigs_in_db} signature relationships, {total_keys_in_db} PGP keys, {commits_with_sigs} commits with signatures")
    if error_count > 0:
        print(f"Encountered {error_count} errors during processing")
        if sample_errors:
            print(f"Sample errors: {', '.join(sample_errors)}")
    
    return total_signed


def process_tag_signatures(repo: Repo, db: Neo4jDriver):
    """
    Extract and store PGP signatures for tags already in the database.
    
    This function works on existing tags, making it safe to run independently.
    It queries for TagObjects without HAS_SIGNATURE relationships and processes them.
    
    Args:
        repo: Git repository
        db: Neo4j driver
    """
    # Query database for TagObjects that don't have signatures yet
    with db._driver.session() as session:
        query = """
        MATCH (to:TagObject)
        WHERE NOT (to)-[:HAS_SIGNATURE]->(:PGPKey)
        RETURN to.name AS name
        """
        result = session.run(query)
        tag_names = [record["name"] for record in result]
    
    if not tag_names:
        print("No tags without signatures found")
        return
    
    print(f"Processing signatures for {len(tag_names)} tags")
    
    # Extract signatures and collect data
    key_rows = []
    signature_rows = []
    seen_fingerprints = set()
    
    for tag_name in tag_names:
        try:
            tag_ref = repo.tags[tag_name]
            sig_data = extract_tag_signature(tag_ref)
            
            if sig_data and sig_data.get('fingerprint'):
                fingerprint = sig_data['fingerprint']
                
                # Collect unique PGP keys
                if fingerprint not in seen_fingerprints:
                    key_rows.append({
                        'fingerprint': fingerprint,
                        'createdAt': None,  # Can be populated later
                        'revokedAt': None
                    })
                    seen_fingerprints.add(fingerprint)
                
                # Collect signature relationships
                signature_rows.append({
                    'artifact_type': 'TagObject',
                    'artifact_id': tag_name,
                    'fingerprint': fingerprint,
                    'valid': sig_data.get('valid'),
                    'method': sig_data.get('method', 'gpg')
                })
        except Exception as e:
            print(f"Error processing signature for tag {tag_name}: {e}")
            continue
    
    # Batch upsert PGP keys
    if key_rows:
        db.batch_upsert_pgp_keys(key_rows)
        print(f"Upserted {len(key_rows)} PGP keys")
    
    # Batch create signature relationships
    if signature_rows:
        db.batch_create_signatures(signature_rows)
        print(f"Created {len(signature_rows)} signature relationships")
    
    unsigned_count = len(tag_names) - len(signature_rows)
    if unsigned_count > 0:
        print(f"Found {unsigned_count} unsigned tags")


def process_merged_includes(
    repo: Repo,
    db: Neo4jDriver,
    merge_limit: Optional[int] = None
) -> int:
    """
    Compute and store MERGED_INCLUDES relationships for merge commits.
    
    Returns:
        int: Number of MERGED_INCLUDES relationships created
    """
    BATCH_SIZE = 100
    
    # Query database for merge commits without MERGED_INCLUDES relationships
    with db._driver.session() as session:
        # Get total merge commit count
        total_merges_result = session.run("MATCH (c:Commit {isMerge: true}) RETURN count(c) AS count")
        total_merges_record = total_merges_result.single()
        total_merges = total_merges_record["count"] if total_merges_record else 0
        
        # Count merges with MERGED_INCLUDES relationships
        # May produce warnings if relationship type doesn't exist yet, but query still works
        merges_with_includes_result = session.run(
            "MATCH (c:Commit {isMerge: true})-[:MERGED_INCLUDES]->() RETURN count(DISTINCT c) AS count"
        )
        merges_with_includes_record = merges_with_includes_result.single()
        merges_with_includes = merges_with_includes_record["count"] if merges_with_includes_record else 0
        
        if merge_limit:
            query = """
            MATCH (c:Commit {isMerge: true})
            WHERE NOT (c)-[:MERGED_INCLUDES]->()
            RETURN c.commit_hash AS sha
            ORDER BY c.committedAt DESC
            LIMIT $limit
            """
            result = session.run(query, limit=merge_limit)
        else:
            query = """
            MATCH (c:Commit {isMerge: true})
            WHERE NOT (c)-[:MERGED_INCLUDES]->()
            RETURN c.commit_hash AS sha
            ORDER BY c.committedAt DESC
            """
            result = session.run(query)
        
        merge_shas = [record["sha"] for record in result]
    
    if not merge_shas:
        print("No merge commits without MERGED_INCLUDES relationships found")
        return
    
    print(f"MERGED_INCLUDES processing status: {total_merges} total merges, {merges_with_includes} already processed, {len(merge_shas)} need processing")
    print(f"Processing MERGED_INCLUDES for {len(merge_shas)} merge commits")
    
    # Process merges and collect data in batches
    merge_rows = []
    
    # Track statistics across batches
    total_processed = 0
    total_relationships = 0
    error_count = 0
    
    for i, merge_sha in enumerate(merge_shas, 1):
        try:
            merge_commit = repo.commit(merge_sha)
            
            # Compute commits introduced by this merge
            included_shas = compute_merged_commits(merge_commit, repo)
            
            if included_shas:
                # Collect data for batch creation
                merge_rows.append({
                    'merge_sha': merge_sha,
                    'included_shas': included_shas
                })
                total_relationships += len(included_shas)
            
            total_processed += 1
            
        except Exception as e:
            error_count += 1
            if error_count <= 10 or error_count % 100 == 0:
                print(f"Error processing merge {merge_sha[:8]}: {e}")
            continue
        
        # Save batch every BATCH_SIZE merges
        if i % BATCH_SIZE == 0:
            if merge_rows:
                db.batch_create_merged_includes(merge_rows)
                print(f"Processed {i}/{len(merge_shas)} merges... (created {total_relationships} MERGED_INCLUDES relationships so far)")
                merge_rows = []  # Clear after saving
    
    # Save remaining data (final batch)
    if merge_rows:
        db.batch_create_merged_includes(merge_rows)
        print(f"Created {len(merge_rows)} merge relationships in final batch")
    
    # Verify final database state
    with db._driver.session() as session:
        # Count total MERGED_INCLUDES relationships
        includes_count_result = session.run("MATCH ()-[r:MERGED_INCLUDES]->() RETURN count(r) AS count")
        includes_count_record = includes_count_result.single()
        total_includes_in_db = includes_count_record["count"] if includes_count_record else 0
        
        # Count merges with MERGED_INCLUDES
        merges_with_includes_result = session.run(
            "MATCH (c:Commit {isMerge: true})-[:MERGED_INCLUDES]->() RETURN count(DISTINCT c) AS count"
        )
        merges_with_includes_record = merges_with_includes_result.single()
        merges_with_includes_final = merges_with_includes_record["count"] if merges_with_includes_record else 0
    
    print(f"Completed: processed {total_processed} merges, created {total_relationships} MERGED_INCLUDES relationships")
    print(f"Database state: {total_includes_in_db} total MERGED_INCLUDES relationships, {merges_with_includes_final} merges with relationships")
    if error_count > 0:
        print(f"Encountered {error_count} errors during processing")
    
    return total_relationships


if __name__ == "__main__":
    process_git_data()
