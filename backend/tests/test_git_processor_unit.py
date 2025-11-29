from git_processor import find_commits_in_repo, find_relevant_commits


def test_find_commits_in_repo_in_chronological_order(sample_git_repo):
    commits = find_commits_in_repo(sample_git_repo.repo)
    messages = [str(commit.message).strip() for commit in commits]

    assert messages[0] == "Initial commit"
    assert messages[-1].startswith("Merge feature")
    assert len(commits) == len(sample_git_repo.commits)


def test_find_commits_in_repo_respects_limit(sample_git_repo):
    commits = find_commits_in_repo(sample_git_repo.repo, limit=2)
    assert len(commits) == 2
    assert commits[0].message.strip() == "Initial commit"


def test_find_relevant_commits_counts(sample_git_repo):
    result = find_relevant_commits(sample_git_repo.repo, "src/consensus")
    assert result["length_of_all_commits"] == 1
    assert result["length_of_unique_authors"] == 1
    assert "Carol" in result["unique_author_names"]
    assert result["master_sha_at_collection"] == sample_git_repo.repo.heads.master.commit.hexsha


def test_find_relevant_commits_handles_missing_path(sample_git_repo):
    result = find_relevant_commits(sample_git_repo.repo, "does/not/exist")
    assert result["length_of_all_commits"] == 0
    assert result["length_of_unique_authors"] == 0

