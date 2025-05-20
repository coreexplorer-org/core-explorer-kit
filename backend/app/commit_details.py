
from typing import List, Optional
from git import Commit, Actor

class CommitDetails:
    """
    Represents the details of a Git commit.
    
    Attributes:
        commit_hash (str): The hash of the commit.
        author (str): The name of the author of the commit.
        author_email (str): The email of the author of the commit.
        authored_date (int): The timestamp of when the commit was authored.
        committer (str): The name of the committer of the commit.
        committer_email (str): The email of the committer of the commit.
        committed_date (int): The timestamp of when the commit was committed.
        message (str): The commit message.
        parent_shas (List[str]): The hashes of the parent commits.
        parents (List[Commit]): The parent commits.
        files_changed (List[str]): The list of files changed in the commit.
        summary (str): The summary of the commit.
        co_authors (List[str]): The list of co-authors of the commit.
    """
    
    def __init__(self, commit: Commit) -> None:
        """
        Initializes a new instance of the CommitDetails class.
        
        Args:
            commit (Commit): The Git commit object to extract details from.
        """
        self.commit_hash: str = commit.hexsha
        self.author: Actor = commit.author
        self.author_name = commit.author.name
        self.author_email: str = commit.author.email
        self.authored_date: int = commit.authored_date
        self.committer: Actor = commit.committer
        self.committer_name: str = commit.committer.name
        self.committer_email: str = commit.committer.email
        self.committed_date: int = commit.committed_date
        self.message: str = commit.message
        self.parent_shas: List[str] = [parent.hexsha for parent in commit.parents]
        self.parents: List[Commit] = commit.parents
        # self.files_changed: List[str] = [diff.a_path for diff in commit.diff('HEAD~1')]
        self.summary: str = commit.summary
        self.co_authors: List[str] = commit.co_authors
        # self.insertions: int = sum(diff.stats['insertions'] for diff in commit.diff('HEAD~1'))
        # self.deletions: int = sum(diff.stats['deletions'] for diff in commit.diff('HEAD~1'))
        
    def get_insertions(self) -> int:
        """
        Returns the number of insertions in the commit.
        
        Returns:
            int: The number of insertions.
        """
        return self.insertions
    
    def get_deletions(self) -> int:
        """
        Returns the number of deletions in the commit.
        
        Returns:
            int: The number of deletions.
        """
        return self.deletions
