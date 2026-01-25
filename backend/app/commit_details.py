
from typing import List, Optional
from datetime import datetime
from git import Commit, Actor

class CommitDetails:
    """
    Represents the details of a Git commit.
    
    Attributes:
        commit_hash (str): The hash of the commit.
        author (Actor): The author of the commit.
        author_name (str): The name of the author.
        author_email (str): The email of the author.
        authored_date (int): The timestamp of when the commit was authored.
        authored_datetime (datetime): The datetime of when the commit was authored.
        committer (Actor): The committer of the commit.
        committer_name (str): The name of the committer.
        committer_email (str): The email of the committer.
        committed_date (int): The timestamp of when the commit was committed.
        committed_datetime (datetime): The datetime of when the commit was committed.
        message (str): The commit message.
        summary (str): The summary of the commit.
        parent_shas (List[str]): The hashes of the parent commits.
        parents (List[Commit]): The parent commits.
        isMerge (bool): Whether this is a merge commit (has more than one parent).
        co_authors (List[Actor]): The list of co-authors of the commit (from Co-authored-by trailers).
    """
    
    def __init__(self, commit: Commit) -> None:
        """
        Initializes a new instance of the CommitDetails class.
        
        Args:
            commit (Commit): The Git commit object to extract details from.
        """
        self.commit_hash: str = commit.hexsha
        self.author: Actor = commit.author
        self.author_name: str = commit.author.name
        self.author_email: str = commit.author.email
        self.authored_date: int = commit.authored_date
        self.authored_datetime: datetime = commit.authored_datetime
        self.committer: Actor = commit.committer
        self.committer_name: str = commit.committer.name
        self.committer_email: str = commit.committer.email
        self.committed_date: int = commit.committed_date
        self.committed_datetime: datetime = commit.committed_datetime
        self.message: str = commit.message
        self.summary: str = commit.summary
        self.parent_shas: List[str] = [parent.hexsha for parent in commit.parents]
        self.parents: List[Commit] = commit.parents
        self.isMerge: bool = len(commit.parents) > 1
        # co_authors returns List[Actor] from GitPython
        self.co_authors: List[Actor] = list(commit.co_authors) if hasattr(commit, 'co_authors') else []
