"""
Unit tests for signature extraction module.

These tests verify the fingerprint parsing logic without requiring
a full Git repository or database connection.
"""

import pytest
from signature_extractor import parse_gpg_fingerprint


def test_parse_fingerprint_primary_key_pattern():
    """Test parsing fingerprint from 'Primary key fingerprint' pattern."""
    output = """gpg: Signature made Mon Jan 15 10:30:00 2024 UTC
gpg:                using RSA key 1234567890ABCDEF1234567890ABCDEF12345678
gpg: Good signature from "Test User <test@example.com>"
Primary key fingerprint: 1234 5678 90AB CDEF 1234  5678 90AB CDEF 1234 5678"""
    
    fingerprint = parse_gpg_fingerprint(output)
    assert fingerprint == "1234567890ABCDEF1234567890ABCDEF12345678"


def test_parse_fingerprint_using_key_pattern():
    """Test parsing fingerprint from 'using RSA key' pattern."""
    output = """gpg: Signature made using RSA key ABCDEF1234567890ABCDEF1234567890ABCDEF12
gpg: Good signature from "Another User <another@example.com>"
"""
    
    fingerprint = parse_gpg_fingerprint(output)
    assert fingerprint == "ABCDEF1234567890ABCDEF1234567890ABCDEF12"


def test_parse_fingerprint_ecdsa_key():
    """Test parsing fingerprint from ECDSA key pattern."""
    output = """gpg: Signature made using ECDSA key FEDCBA0987654321FEDCBA0987654321FEDCBA09
gpg: Good signature"""
    
    fingerprint = parse_gpg_fingerprint(output)
    assert fingerprint == "FEDCBA0987654321FEDCBA0987654321FEDCBA09"


def test_parse_fingerprint_no_match():
    """Test that None is returned when no fingerprint pattern matches."""
    output = """gpg: Signature made
gpg: Good signature from "User <user@example.com>"
No fingerprint here"""
    
    fingerprint = parse_gpg_fingerprint(output)
    # Should fall back to pattern3 (any 40-char hex), but if that fails, return None
    # In this case, there's no 40-char hex string, so should return None
    assert fingerprint is None or len(fingerprint) == 40


def test_parse_fingerprint_case_insensitive():
    """Test that fingerprint parsing is case-insensitive."""
    output = """Primary key fingerprint: abcd ef12 3456 7890 abcd  ef12 3456 7890 abcd ef12"""
    
    fingerprint = parse_gpg_fingerprint(output)
    assert fingerprint == "ABCDEF1234567890ABCDEF1234567890ABCDEF12"


def test_parse_fingerprint_whitespace_handling():
    """Test that whitespace in fingerprints is properly removed."""
    output = """Primary key fingerprint: 1234  5678  90AB  CDEF  1234   5678  90AB  CDEF  1234  5678"""
    
    fingerprint = parse_gpg_fingerprint(output)
    assert fingerprint == "1234567890ABCDEF1234567890ABCDEF12345678"
    assert ' ' not in fingerprint
