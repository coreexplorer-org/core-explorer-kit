"""
Module for computing ancestry delta for merge commits.

This module computes which commits are introduced by a merge commit,
i.e., commits reachable from the second parent but not from the first parent.
"""
from typing import List, Set
import logging
from git import Commit, Repo

logger = logging.getLogger(__name__)


def compute_merged_commits(merge_commit: Commit, repo: Repo) -> List[str]:
    """
    Compute the set of commits introduced by a merge commit.
    
    For a merge commit M with parents P1 (first) and P2 (second),
    this computes: commits reachable from P2 that are NOT reachable from P1.
    
    Args:
        merge_commit: The merge commit object
        repo: The Git repository object
        
    Returns:
        List of commit SHAs (hex strings) introduced by the merge.
        Returns empty list if:
        - Commit is not a merge (has < 2 parents)
        - Merge introduces no new commits
        - Error occurs during computation
    """
    # Check if this is actually a merge commit
    if len(merge_commit.parents) < 2:
        return []  # Not a merge
    
    try:
        first_parent = merge_commit.parents[0]
        second_parent = merge_commit.parents[1]
        merge_sha = merge_commit.hexsha
        
        # Collect commits reachable from second parent
        # We walk the ancestry from P2 until we hit P1 or run out of commits
        second_parent_commits: Set[str] = set()
        for commit in repo.iter_commits(second_parent):
            commit_sha = commit.hexsha
            second_parent_commits.add(commit_sha)
            
            # Stop if we've reached the first parent (common ancestor)
            if commit_sha == first_parent.hexsha:
                break
        
        # Collect commits reachable from first parent
        # We need this to compute the difference
        first_parent_commits: Set[str] = set()
        for commit in repo.iter_commits(first_parent):
            first_parent_commits.add(commit.hexsha)
        
        # Commits introduced by merge = commits in P2 that are not in P1
        merged_commits = second_parent_commits - first_parent_commits
        
        # Exclude the merge commit itself
        merged_commits.discard(merge_sha)
        
        return list(merged_commits)
        
    except Exception as e:
        # Handle errors gracefully (missing commits, corrupted history, etc.)
        logger.error(f"Error computing merged commits for {merge_commit.hexsha[:8]}: {e}")
        return []
