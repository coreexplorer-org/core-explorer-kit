# src/signature_extractor.py
"""
Module for extracting PGP signatures from Git commits and tags.

This module uses git CLI commands to extract signature information,
as GitPython doesn't directly expose GPG signature data.
"""

from typing import Optional, Dict, Any
import subprocess
import re
from git import Commit, TagReference, Repo


def extract_commit_signature(commit: Commit) -> Optional[Dict[str, Any]]:
    """
    Extract PGP signature information from a Git commit.
    
    Args:
        commit: Git commit object
        
    Returns:
        Dict with keys: fingerprint, method, valid (None initially)
        Returns None if no signature found
    """
    try:
        # Use git show --show-signature to get signature information
        repo = commit.repo
        result = subprocess.run(
            ['git', 'show', '--show-signature', commit.hexsha],
            cwd=repo.working_dir or repo.git_dir,
            capture_output=True,
            text=False,  # Get bytes, decode manually
            timeout=10
        )
        
        # Decode with error handling to gracefully handle binary PGP signature data
        # Note: git show --show-signature can return non-zero exit code even when signature exists
        # (e.g., if signature is invalid or key is untrusted), so we check output regardless
        # Also note: git may output signature info to stderr, not stdout!
        try:
            stdout = result.stdout.decode('utf-8', errors='replace') if result.stdout else ''
            stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ''
            # Combine stdout and stderr - git often puts signature info in stderr
            output = stdout + '\n' + stderr
        except Exception:
            # Fallback: try latin-1 which can decode any byte
            stdout = result.stdout.decode('latin-1', errors='replace') if result.stdout else ''
            stderr = result.stderr.decode('latin-1', errors='replace') if result.stderr else ''
            output = stdout + '\n' + stderr
        
        # Check if signature exists (look for signature indicators)
        # git show --show-signature outputs signature info even if validation fails
        # Look for various indicators of signature presence
        # Note: We check for specific GPG-related strings to avoid false positives
        has_signature_indicator = (
            'gpg:' in output or 
            'Good signature' in output or 
            'Bad signature' in output or
            'Primary key fingerprint:' in output or
            'using RSA key' in output or
            'using ECDSA key' in output or
            'using EDDSA key' in output or
            'using DSA key' in output
        )
        
        if not has_signature_indicator:
            return None
        
        # Extract fingerprint from output
        fingerprint = parse_gpg_fingerprint(output)
        
        if fingerprint:
            return {
                'fingerprint': fingerprint,
                'method': 'gpg',
                'valid': None  # Validation deferred to future phase
            }
        
        return None
        
    except subprocess.TimeoutExpired:
        print(f"Timeout extracting signature from commit {commit.hexsha[:8]}")
        return None
    except UnicodeDecodeError as e:
        print(f"Error extracting signature from commit {commit.hexsha[:8]}: {e}")
        return None
    except Exception as e:
        print(f"Error extracting signature from commit {commit.hexsha[:8]}: {e}")
        return None


def extract_tag_signature(tag_ref: TagReference) -> Optional[Dict[str, Any]]:
    """
    Extract PGP signature information from a Git tag.
    
    Args:
        tag_ref: Git tag reference object
        
    Returns:
        Dict with keys: fingerprint, method, valid (None initially)
        Returns None if no signature found (e.g., lightweight tags)
    """
    try:
        # Lightweight tags don't have signatures
        if tag_ref.tag is None:
            return None
        
        repo = tag_ref.repo
        result = subprocess.run(
            ['git', 'show', '--show-signature', tag_ref.name],
            cwd=repo.working_dir or repo.git_dir,
            capture_output=True,
            text=False,  # Get bytes, decode manually
            timeout=10
        )
        
        # Decode with error handling to gracefully handle binary PGP signature data
        # Note: git show --show-signature can return non-zero exit code even when signature exists
        try:
            output = result.stdout.decode('utf-8', errors='replace')
        except Exception:
            # Fallback: try latin-1 which can decode any byte
            output = result.stdout.decode('latin-1', errors='replace')
        
        # Check if signature exists (look for signature indicators)
        has_signature_indicator = (
            'gpg:' in output or 
            'Good signature' in output or 
            'Bad signature' in output or
            'Primary key fingerprint:' in output or
            'using RSA key' in output or
            'using ECDSA key' in output or
            'using EDDSA key' in output or
            'using DSA key' in output
        )
        
        if not has_signature_indicator:
            return None
        
        # Extract fingerprint from output
        fingerprint = parse_gpg_fingerprint(output)
        
        if fingerprint:
            return {
                'fingerprint': fingerprint,
                'method': 'gpg',
                'valid': None  # Validation deferred to future phase
            }
        
        return None
        
    except subprocess.TimeoutExpired:
        print(f"Timeout extracting signature from tag {tag_ref.name}")
        return None
    except Exception as e:
        print(f"Error extracting signature from tag {tag_ref.name}: {e}")
        return None


def parse_gpg_fingerprint(git_show_output: str) -> Optional[str]:
    """
    Parse GPG fingerprint from git show --show-signature output.
    
    Looks for lines like:
    - "Primary key fingerprint: XXXX XXXX XXXX ..."
    - "gpg: Signature made ... using RSA key XXXX..."
    
    Args:
        git_show_output: Output from git show --show-signature
        
    Returns:
        40-character fingerprint (spaces removed) or None if not found
    """
    # Pattern 1: "Primary key fingerprint: XXXX XXXX ..."
    pattern1 = r'Primary key fingerprint:\s*([0-9A-F]{4}(?:\s+[0-9A-F]{4}){9})'
    match = re.search(pattern1, git_show_output, re.IGNORECASE)
    if match:
        fingerprint = match.group(1).replace(' ', '').upper()
        if len(fingerprint) == 40:
            return fingerprint
    
    # Pattern 2: "using RSA key XXXX..." or "using ECDSA key XXXX..."
    pattern2 = r'using\s+(?:RSA|ECDSA|EDDSA|DSA)\s+key\s+([0-9A-F]{40})'
    match = re.search(pattern2, git_show_output, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    
    # Pattern 3: Look for fingerprint in "key ID" or "Key ID" context (more restrictive)
    # Only match if it's clearly in a key/fingerprint context
    pattern3 = r'(?:key\s+id|keyid|fingerprint)[\s:]*([0-9A-F]{40})'
    match = re.search(pattern3, git_show_output, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    
    # Don't use the fallback pattern that matches any 40-char hex string
    # This was causing false positives (matching commit hashes, etc.)
    return None
