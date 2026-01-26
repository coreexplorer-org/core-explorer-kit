#!/usr/bin/env python3
"""
Test script for signature extraction functionality.

This script tests the signature extraction module with actual commits/tags
from the repository to verify extraction works correctly.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from git import Repo
import config
from signature_extractor import extract_commit_signature, extract_tag_signature, parse_gpg_fingerprint


def test_commit_signature_extraction(repo_path: str, num_commits: int = 10):
    """Test signature extraction on commits."""
    print(f"\n=== Testing Commit Signature Extraction ===")
    repo = Repo(repo_path)
    
    signed_count = 0
    unsigned_count = 0
    error_count = 0
    
    # Test on recent commits
    for i, commit in enumerate(repo.iter_commits(max_count=num_commits)):
        try:
            sig_data = extract_commit_signature(commit)
            if sig_data:
                print(f"✓ Commit {commit.hexsha[:8]}: SIGNED")
                print(f"  Fingerprint: {sig_data.get('fingerprint', 'N/A')}")
                print(f"  Method: {sig_data.get('method', 'N/A')}")
                signed_count += 1
            else:
                print(f"○ Commit {commit.hexsha[:8]}: UNSIGNED")
                unsigned_count += 1
        except Exception as e:
            print(f"✗ Commit {commit.hexsha[:8]}: ERROR - {e}")
            error_count += 1
    
    print(f"\nResults: {signed_count} signed, {unsigned_count} unsigned, {error_count} errors")
    return signed_count, unsigned_count, error_count


def test_tag_signature_extraction(repo_path: str):
    """Test signature extraction on tags."""
    print(f"\n=== Testing Tag Signature Extraction ===")
    repo = Repo(repo_path)
    
    signed_count = 0
    unsigned_count = 0
    error_count = 0
    
    # Test on all tags
    tags = list(repo.tags)
    if not tags:
        print("No tags found in repository")
        return 0, 0, 0
    
    print(f"Found {len(tags)} tags")
    
    for tag_ref in tags[:10]:  # Test first 10 tags
        try:
            sig_data = extract_tag_signature(tag_ref)
            if sig_data:
                print(f"✓ Tag {tag_ref.name}: SIGNED")
                print(f"  Fingerprint: {sig_data.get('fingerprint', 'N/A')}")
                print(f"  Method: {sig_data.get('method', 'N/A')}")
                signed_count += 1
            else:
                print(f"○ Tag {tag_ref.name}: UNSIGNED (or lightweight tag)")
                unsigned_count += 1
        except Exception as e:
            print(f"✗ Tag {tag_ref.name}: ERROR - {e}")
            error_count += 1
    
    print(f"\nResults: {signed_count} signed, {unsigned_count} unsigned, {error_count} errors")
    return signed_count, unsigned_count, error_count


def test_fingerprint_parsing():
    """Test fingerprint parsing with sample git show output."""
    print(f"\n=== Testing Fingerprint Parsing ===")
    
    # Sample output from git show --show-signature
    sample_outputs = [
        """gpg: Signature made Mon Jan 15 10:30:00 2024 UTC
gpg:                using RSA key 1234567890ABCDEF1234567890ABCDEF12345678
gpg: Good signature from "Test User <test@example.com>"
Primary key fingerprint: 1234 5678 90AB CDEF 1234  5678 90AB CDEF 1234 5678""",
        
        """gpg: Signature made using ECDSA key ABCDEF1234567890ABCDEF1234567890ABCDEF12
gpg: Good signature from "Another User <another@example.com>"
Primary key fingerprint: ABCD EF12 3456 7890 ABCD  EF12 3456 7890 ABCD EF12""",
    ]
    
    for i, output in enumerate(sample_outputs, 1):
        fingerprint = parse_gpg_fingerprint(output)
        if fingerprint:
            print(f"✓ Sample {i}: Extracted fingerprint {fingerprint}")
        else:
            print(f"✗ Sample {i}: Failed to extract fingerprint")


if __name__ == "__main__":
    # Try to find repository path
    repo_path = os.getenv("CONTAINER_SIDE_REPOSITORY_PATH", config.CONTAINER_SIDE_REPOSITORY_PATH)
    
    # Check common locations
    if not os.path.exists(repo_path):
        # Try parent directory or common locations
        possible_paths = [
            os.path.expanduser("~/bitcoin"),
            os.path.expanduser("~/code/bitcoin"),
            "/tmp/bitcoin",
            "../bitcoin",
        ]
        for path in possible_paths:
            if os.path.exists(path) and os.path.isdir(os.path.join(path, ".git")):
                repo_path = path
                print(f"Found repository at: {repo_path}")
                break
        else:
            print(f"Repository path does not exist: {repo_path}")
            print("\nTo test signature extraction, you need a Git repository.")
            print("Options:")
            print("1. Set CONTAINER_SIDE_REPOSITORY_PATH environment variable")
            print("2. Clone a repository (e.g., git clone https://github.com/bitcoin/bitcoin.git)")
            print("3. Update config.py with your repository path")
            print("\nFor now, testing fingerprint parsing only...")
            test_fingerprint_parsing()
            sys.exit(0)
    
    print(f"Testing signature extraction on repository: {repo_path}")
    
    # Test fingerprint parsing first (doesn't require repo)
    test_fingerprint_parsing()
    
    # Test commit signature extraction
    signed_commits, unsigned_commits, commit_errors = test_commit_signature_extraction(repo_path, num_commits=20)
    
    # Test tag signature extraction
    signed_tags, unsigned_tags, tag_errors = test_tag_signature_extraction(repo_path)
    
    print(f"\n=== Summary ===")
    print(f"Commits: {signed_commits} signed, {unsigned_commits} unsigned, {commit_errors} errors")
    print(f"Tags: {signed_tags} signed, {unsigned_tags} unsigned, {tag_errors} errors")
    
    if commit_errors > 0 or tag_errors > 0:
        print("\n⚠️  Some errors occurred during extraction. Check output above.")
        sys.exit(1)
    else:
        print("\n✓ All tests completed successfully!")
