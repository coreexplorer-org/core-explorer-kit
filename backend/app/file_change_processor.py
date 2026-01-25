"""
Utility functions for computing file-level changes from Git commits.
"""
from typing import List, Dict, Optional, Set
from git import Commit, Diff
from datetime import datetime


# Sensitive path patterns (can be extended)
SENSITIVE_PATHS = [
    "src/policy",
    "src/consensus",
    "src/rpc/mempool.cpp",
    "contrib/verify-commits",  # Maintainer key list is here: contrib/verify-commits/trusted-keys
    "contrib/verify-binaries"
]


def is_sensitive_path(path: str) -> bool:
    """Check if a path matches sensitive patterns."""
    return any(path.startswith(prefix) for prefix in SENSITIVE_PATHS)


def compute_file_changes(commit: Commit, sensitive_paths: Optional[Set[str]] = None) -> List[Dict]:
    """
    Compute file-level changes for a commit by diffing against its first parent.
    
    Args:
        commit: The Git commit object
        sensitive_paths: Optional set of sensitive path prefixes (defaults to SENSITIVE_PATHS)
    
    Returns:
        List of dicts with keys: path, status, add, del, rename_from, isSensitive
    """
    if sensitive_paths is None:
        sensitive_paths = set(SENSITIVE_PATHS)
    
    changes = []
    
    # For root commits, diff against empty tree
    # Use create_patch=True to get diff content for stats computation
    if len(commit.parents) == 0:
        diffs = commit.diff(None, create_patch=True)
    else:
        # Diff against first parent (mainline change)
        diffs = commit.diff(commit.parents[0], create_patch=True)
    
    for diff in diffs:
        # Determine status
        if diff.new_file:
            status = "A"  # Added
        elif diff.deleted_file:
            status = "D"  # Deleted
        elif diff.renamed_file:
            status = "R"  # Renamed
        else:
            status = "M"  # Modified
        
        # Get paths
        path = diff.b_path if diff.b_path else diff.a_path
        rename_from = diff.a_path if diff.renamed_file and diff.a_path != path else None
        
        # Get stats (insertions/deletions)
        # GitPython Diff doesn't have stats attribute directly, so we compute from diff
        add = 0
        del_count = 0
        try:
            # Get the diff content and count additions/deletions
            if hasattr(diff, 'diff') and diff.diff:
                diff_bytes = diff.diff
                if isinstance(diff_bytes, bytes):
                    diff_text = diff_bytes.decode('utf-8', errors='ignore')
                else:
                    diff_text = str(diff_bytes)
                
                # Count lines: + for additions, - for deletions
                # Exclude file headers (+++, ---) and context lines (space)
                for line in diff_text.split('\n'):
                    if line.startswith('+') and not line.startswith('+++'):
                        add += 1
                    elif line.startswith('-') and not line.startswith('---'):
                        del_count += 1
        except (AttributeError, UnicodeDecodeError, Exception) as e:
            # If we can't compute stats, leave as 0
            # This is acceptable - we still have the path and status which are most important
            pass
        
        # Check if sensitive
        is_sensitive = any(path.startswith(prefix) for prefix in sensitive_paths)
        
        changes.append({
            "path": path,
            "status": status,
            "add": add,
            "del": del_count,
            "rename_from": rename_from,
            "isSensitive": is_sensitive,
        })
    
    return changes


def compute_file_changes_for_paths(
    commit: Commit,
    target_paths: List[str],
    sensitive_paths: Optional[Set[str]] = None
) -> List[Dict]:
    """
    Compute file-level changes for a commit, filtering to only include changes
    that touch any of the target paths.
    
    Args:
        commit: The Git commit object
        target_paths: List of paths or path prefixes to filter by
        sensitive_paths: Optional set of sensitive path prefixes
    
    Returns:
        List of dicts with keys: path, status, add, del, rename_from, isSensitive
    """
    all_changes = compute_file_changes(commit, sensitive_paths)
    
    # Filter to target paths
    filtered = []
    for change in all_changes:
        path = change["path"]
        if any(path.startswith(target) or target.startswith(path) for target in target_paths):
            filtered.append(change)
    
    return filtered
