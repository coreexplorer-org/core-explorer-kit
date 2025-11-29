from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Iterator

import pytest
from git import Actor, Repo
from testcontainers.neo4j import Neo4jContainer

from neo4j_driver import Neo4jDriver


TEST_NEO4J_PASSWORD = "core-explorer"


@dataclass
class RepoContext:
    repo: Repo
    path: str
    commits: List[str]
    folder_commit_counts: Dict[str, int]
    unique_authors: List[str]


@pytest.fixture(scope="session")
def neo4j_container() -> Iterator[Neo4jContainer]:
    container = Neo4jContainer(
        image="neo4j:5.20.0",
        password=TEST_NEO4J_PASSWORD,
    )
    container.start()
    yield container
    container.stop()


@pytest.fixture
def neo4j_driver(neo4j_container: Neo4jContainer) -> Iterator[Neo4jDriver]:
    driver = Neo4jDriver(
        uri=neo4j_container.get_connection_url(),
        user="neo4j",
        password=TEST_NEO4J_PASSWORD,
    )
    driver.clear_database()
    yield driver
    driver.clear_database()
    driver.close()


@pytest.fixture
def sample_git_repo(tmp_path: Path) -> RepoContext:
    repo_path = tmp_path / "sample-repo"
    repo = Repo.init(repo_path, initial_branch="master")

    actors = {
        "alice": Actor("Alice", "alice@example.com"),
        "bob": Actor("Bob", "bob@example.com"),
        "carol": Actor("Carol", "carol@example.com"),
        "dave": Actor("Dave", "dave@example.com"),
    }

    def commit_file(
        relative_path: str,
        content: str,
        message: str,
        author: Actor,
        committer: Actor | None = None,
    ):
        file_path = repo_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        repo.index.add([str(file_path)])
        return repo.index.commit(
            message,
            author=author,
            committer=committer or author,
        )

    commits = []
    commits.append(
        commit_file("README.md", "initial readme\n", "Initial commit", actors["alice"])
    )
    commits.append(
        commit_file(
            "src/policy/policy.cpp",
            "bool CheckPolicy() { return true; }\n",
            "Add policy logic",
            actors["bob"],
        )
    )

    feature_branch = repo.create_head("feature", commits[-1])
    feature_branch.checkout()

    consensus_message = (
        "Consensus update\n\nCo-authored-by: Dave <dave@example.com>\n"
    )
    feature_commit = commit_file(
        "src/consensus/consensus.cpp",
        "int EnforceConsensus() { return 1; }\n",
        consensus_message,
        actors["carol"],
    )
    commits.append(feature_commit)
    feature_tip = feature_commit

    repo.git.checkout("master")
    commits.append(
        commit_file(
            "src/rpc/mempool.cpp",
            "void RpcMempool() {}\n",
            "RPC tweaks",
            actors["alice"],
        )
    )
    merge_commit = repo.index.commit(
        "Merge feature into master",
        author=actors["alice"],
        committer=actors["alice"],
        parent_commits=[repo.head.commit, feature_tip],
    )
    commits.append(merge_commit)

    return RepoContext(
        repo=repo,
        path=str(repo_path),
        commits=[commit.hexsha for commit in commits],
        folder_commit_counts={
            "src/policy": 1,
            "src/consensus": 1,
            "src/rpc/mempool.cpp": 1,
        },
        unique_authors=["Alice", "Bob", "Carol", "Dave"],
    )

