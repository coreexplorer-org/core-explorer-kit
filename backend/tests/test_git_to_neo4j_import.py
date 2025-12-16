import json

from git_processor import process_git_data


def _count(session, label):
    query = f"MATCH (n:{label}) RETURN count(n) AS c"
    return session.run(query).single()["c"]


def test_initial_import_creates_nodes(sample_git_repo, neo4j_driver):
    process_git_data(
        repo_path=sample_git_repo.path,
        neo4j_driver=neo4j_driver,
        folder_paths=[],
    )

    with neo4j_driver._driver.session() as session:
        actor_count = _count(session, "Actor")
        commit_count = _count(session, "Commit")
        status = session.run(
            "MATCH (s:ImportStatus) RETURN s.git_import_complete AS flag"
        ).single()["flag"]

    assert actor_count >= 3
    assert commit_count == len(sample_git_repo.commits)
    assert status is True


def test_reimport_is_idempotent(sample_git_repo, neo4j_driver):
    process_git_data(
        repo_path=sample_git_repo.path,
        neo4j_driver=neo4j_driver,
        folder_paths=[],
    )
    with neo4j_driver._driver.session() as session:
        initial_actor_count = _count(session, "Actor")
        initial_commit_count = _count(session, "Commit")

    process_git_data(
        repo_path=sample_git_repo.path,
        neo4j_driver=neo4j_driver,
        folder_paths=[],
    )

    with neo4j_driver._driver.session() as session:
        second_actor_count = _count(session, "Actor")
        second_commit_count = _count(session, "Commit")

    assert (initial_actor_count, initial_commit_count) == (
        second_actor_count,
        second_commit_count,
    )


def test_folder_processing_after_import(sample_git_repo, neo4j_driver):
    process_git_data(
        repo_path=sample_git_repo.path,
        neo4j_driver=neo4j_driver,
        folder_paths=[],
    )
    process_git_data(
        repo_path=sample_git_repo.path,
        neo4j_driver=neo4j_driver,
        folder_paths=["src/policy"],
    )

    with neo4j_driver._driver.session() as session:
        record = session.run(
            """
            MATCH (f:FileDetailRecord {file_path: $path})
            RETURN f.json_blob AS blob
            """,
            path="src/policy",
        ).single()
    payload = json.loads(record["blob"])
    assert payload["length_of_all_commits"] == sample_git_repo.folder_commit_counts[
        "src/policy"
    ]


def test_folder_processing_with_preseeded_status(sample_git_repo, neo4j_driver):
    with neo4j_driver._driver.session() as session:
        session.run(
            """
            MERGE (s:ImportStatus)
            SET s.git_import_complete = true,
                s.next_complete = false
            """
        )

    process_git_data(
        repo_path=sample_git_repo.path,
        neo4j_driver=neo4j_driver,
        folder_paths=["src/consensus"],
    )

    with neo4j_driver._driver.session() as session:
        commit_count = _count(session, "Commit")
        record = session.run(
            """
            MATCH (f:FileDetailRecord {file_path: $path})
            RETURN f.json_blob AS blob
            """,
            path="src/consensus",
        ).single()
    payload = json.loads(record["blob"])

    assert commit_count == 0
    assert payload["length_of_all_commits"] == sample_git_repo.folder_commit_counts[
        "src/consensus"
    ]


def test_count_methods(sample_git_repo, neo4j_driver):
    """Test the new count methods for GraphQL queries."""
    # First complete the git import
    process_git_data(
        repo_path=sample_git_repo.path,
        neo4j_driver=neo4j_driver,
        folder_paths=[],  # No folder paths for initial import
    )

    # Now process folder data which creates FileDetailRecord nodes
    from git_processor import import_bitcoin_path
    import_bitcoin_path("src/consensus", repo_path=sample_git_repo.path, neo4j_driver=neo4j_driver)

    # Test node counts
    actor_count = neo4j_driver.get_node_count("Actor")
    commit_count = neo4j_driver.get_node_count("Commit")
    file_detail_count = neo4j_driver.get_node_count("FileDetailRecord")

    assert actor_count >= 3
    assert commit_count == len(sample_git_repo.commits)
    assert file_detail_count == 1  # We imported one folder

    # Test import status
    status = neo4j_driver.get_import_status()
    assert status is not None
    assert "git_import_complete" in status
    assert status["git_import_complete"] is True

