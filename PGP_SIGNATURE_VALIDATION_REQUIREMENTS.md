# PGP Signature Validation Requirements

**Status:** Fast Follow (Post-Merge Priority)  
**Created:** 2026-01-25  
**Related Branch:** harden_deploy (after merge)

---

## Overview

This document defines the requirements for implementing PGP signature validation against maintainer keys. This is the immediate next priority after merging the harden_deploy branch, which currently extracts PGP signatures but does not validate them.

## Current State

The harden_deploy branch implements:
- ✅ PGP signature extraction from commits and tags
- ✅ `PGPKey` node creation with fingerprint uniqueness
- ✅ `HAS_SIGNATURE` relationship creation
- ✅ Signature metadata storage (fingerprint, method)
- ⚠️ **Missing:** Signature validation against trusted keyring

Current `HAS_SIGNATURE` relationship properties:
- `valid`: Currently always `null` (validation deferred)
- `method`: Always `"gpg"`
- `signer_fp`: PGP key fingerprint

## Functional Requirements

### 1. Maintainer Key Import

**FR-1.1: Key Source Options**
- Support file-based key import from repository (e.g., `contrib/builder-keys/`)
- Support custom keyring path via environment variable
- Support multiple key sources (repository + external keyring)
- Store key metadata in Neo4j:
  - Fingerprint (already exists)
  - Key owner name/email (if available)
  - Trust level (maintainer, contributor, etc.)
  - Source (repository, keyring file, manual import)

**FR-1.2: Key Format Support**
- Support GPG key files (`.asc`, `.gpg`)
- Support keyring directories
- Parse key metadata (name, email, creation date)
- Handle key revocation status

**FR-1.3: Key Management**
- Allow updating keyring without re-importing all signatures
- Track key import timestamp
- Support key expiration/revocation updates

### 2. Signature Validation

**FR-2.1: Validation Process**
- Use `gpg --verify` to validate signatures
- Validate against imported maintainer keys
- Update `HAS_SIGNATURE.valid` property:
  - `true`: Signature valid and from known maintainer
  - `false`: Signature invalid, expired, or from untrusted key
  - `null`: Validation not yet performed (current state)
- Store validation timestamp (`validatedAt`)
- Store validation result details (valid, expired, untrusted, etc.)

**FR-2.2: Validation Modes**
- **Full Validation**: Validate all signatures in database
- **Incremental Validation**: Only validate new signatures
- **Re-validation**: Re-validate existing signatures (e.g., after keyring update)

**FR-2.3: Error Handling**
- Handle missing GPG keys gracefully
- Handle expired signatures
- Handle revoked keys
- Log validation failures for debugging
- Continue processing on individual validation errors

### 3. Query Capabilities

**FR-3.1: Validation Status Queries**
Enable GraphQL/Cypher queries for:
- Commits with valid signatures from known maintainers
- Commits with invalid signatures
- Unsigned commits
- Commits signed by unknown/untrusted keys
- Signature validation status over time (trends)

**FR-3.2: Security Analysis Queries**
Enable queries like:
- "Unsigned commits that touched sensitive paths"
- "Commits with invalid signatures in sensitive areas"
- "Commits signed by keys not in maintainer keyring"
- "Signature validation coverage by path"

**FR-3.3: Reporting**
- Generate reports on signature validation status
- Track validation coverage (percentage of commits validated)
- Identify gaps in signature coverage

## Technical Requirements

### 1. New Module: `signature_validator.py`

**TR-1.1: Core Functions**
```python
def validate_signature(commit: Commit, keyring_path: str) -> Dict[str, Any]:
    """
    Validate a commit's PGP signature against a keyring.
    
    Returns:
        {
            'valid': bool | None,
            'error': str | None,
            'key_fingerprint': str | None,
            'key_trusted': bool,
            'validated_at': datetime
        }
    """

def load_maintainer_keys(keyring_path: str) -> List[Dict[str, Any]]:
    """
    Load maintainer keys from keyring directory or file.
    
    Returns:
        List of dicts with keys: fingerprint, name, email, source, trust_level
    """

def update_signature_validity(
    db: Neo4jDriver,
    commit_sha: str,
    validation_result: Dict[str, Any]
) -> None:
    """
    Update HAS_SIGNATURE relationship with validation results.
    """
```

**TR-1.2: Key Import Functions**
```python
def import_keys_from_directory(keyring_dir: str) -> List[Dict[str, Any]]:
    """Import keys from a directory of .asc/.gpg files."""

def import_keys_from_repository(repo_path: str, key_path: str) -> List[Dict[str, Any]]:
    """Import keys from repository path (e.g., contrib/builder-keys/)."""

def upsert_keys_to_database(db: Neo4jDriver, keys: List[Dict[str, Any]]) -> None:
    """Store key metadata in Neo4j PGPKey nodes."""
```

### 2. Database Schema Updates

**TR-2.1: PGPKey Node Properties**
Add to existing `PGPKey` nodes:
- `name`: Key owner name (optional)
- `email`: Key owner email (optional)
- `source`: Where key was imported from (e.g., "repository", "keyring")
- `trust_level`: Trust level (e.g., "maintainer", "contributor")
- `imported_at`: Timestamp when key was imported
- `revoked_at`: Timestamp when key was revoked (if applicable)

**TR-2.2: HAS_SIGNATURE Relationship Properties**
Update existing properties:
- `valid`: Change from `null` to `true`/`false` after validation
- `validated_at`: Timestamp when validation was performed
- `validation_error`: Error message if validation failed (optional)
- `key_trusted`: Whether the signing key is in trusted keyring

**TR-2.3: New Constraints**
- Consider adding constraint on `PGPKey` for key metadata uniqueness
- Index on `HAS_SIGNATURE.validated_at` for temporal queries

### 3. Integration Points

**TR-3.1: Processing Pipeline Integration**
Add validation step to `process_git_data()`:
```python
# After signature extraction
process_commit_signatures(repo, db, commit_limit=commit_limit)
process_tag_signatures(repo, db)

# NEW: Validate signatures
validate_commit_signatures(repo, db, keyring_path, commit_limit=commit_limit)
validate_tag_signatures(repo, db, keyring_path)
```

**TR-3.2: Standalone Endpoint**
Create new Flask endpoint for on-demand validation:
```python
@app.route("/validate_signatures/")
def validate_signatures():
    """Validate all signatures in database against keyring."""
    keyring_path = os.getenv("MAINTAINER_KEYRING_PATH", "contrib/builder-keys")
    validate_all_signatures(repo, db, keyring_path)
    return "Signature validation complete"
```

**TR-3.3: Batch Processing**
- Process signatures in batches (1000 per batch)
- Update database in transactions
- Progress reporting for long-running validations

### 4. Configuration

**TR-4.1: Environment Variables**
Add to `.env.example`:
```bash
# PGP Signature Validation
MAINTAINER_KEYRING_PATH=contrib/builder-keys  # Path to keyring in repository
EXTERNAL_KEYRING_PATH=                         # Optional external keyring path
VALIDATE_SIGNATURES_ON_IMPORT=true            # Auto-validate during import
```

**TR-4.2: Keyring Path Resolution**
- Check repository path first (e.g., `contrib/builder-keys/`)
- Fall back to external keyring path if provided
- Support absolute and relative paths
- Validate keyring path exists before processing

## Implementation Steps

### Phase 1: Key Import (Week 1)

1. **Research Key Sources**
   - Analyze Bitcoin Core `contrib/builder-keys/` structure
   - Document key file formats
   - Identify key metadata extraction methods

2. **Implement Key Import**
   - Create `import_keys_from_directory()` function
   - Create `import_keys_from_repository()` function
   - Parse key metadata (name, email, fingerprint)
   - Store keys in Neo4j with metadata

3. **Add Database Methods**
   - `batch_upsert_pgp_key_metadata()` in `neo4j_driver.py`
   - Update `PGPKey` nodes with name, email, source, trust_level

### Phase 2: Signature Validation (Week 2)

1. **Implement Validation Logic**
   - Create `validate_signature()` function using `gpg --verify`
   - Handle validation errors gracefully
   - Return structured validation results

2. **Batch Validation**
   - Create `validate_commit_signatures()` function
   - Process signatures in batches
   - Update `HAS_SIGNATURE` relationships

3. **Error Handling**
   - Handle missing keys
   - Handle expired signatures
   - Handle revoked keys
   - Log validation failures

### Phase 3: Integration (Week 3)

1. **Pipeline Integration**
   - Add validation step to `process_git_data()`
   - Make validation optional (configurable)
   - Add progress reporting

2. **Standalone Endpoint**
   - Create `/validate_signatures/` endpoint
   - Support re-validation of existing signatures
   - Support validation of new signatures only

3. **GraphQL Queries**
   - Add queries for validation status
   - Add filters for valid/invalid/unsigned
   - Add queries for security analysis

### Phase 4: Testing & Documentation (Week 4)

1. **Testing**
   - Unit tests for key import
   - Unit tests for signature validation
   - Integration tests with test repository
   - Edge case testing (expired keys, revoked keys)

2. **Documentation**
   - Update README with validation workflow
   - Document keyring management
   - Add query examples for validation status
   - Document configuration options

## Success Criteria

### Functional
- ✅ All extracted signatures can be validated
- ✅ Validation results stored in database
- ✅ Queries can filter by validation status
- ✅ Keyring can be updated without re-importing signatures

### Performance
- ✅ Validation processes 1000+ signatures per minute
- ✅ Batch updates complete in reasonable time
- ✅ No significant impact on import pipeline performance

### Quality
- ✅ Comprehensive error handling
- ✅ Clear error messages
- ✅ Progress reporting for long operations
- ✅ Documentation complete

## Dependencies

### External
- `gnupg` package (already in Dockerfile)
- GPG keyring files or directory
- Access to repository for key import

### Internal
- Existing `signature_extractor.py` (extraction already done)
- Existing `neo4j_driver.py` (database methods)
- Existing `git_processor.py` (integration point)

## Risks & Mitigations

### Risk 1: Keyring Not Available
**Mitigation:** Make validation optional, allow external keyring path

### Risk 2: Validation Performance
**Mitigation:** Batch processing, incremental validation, async option

### Risk 3: Key Format Variations
**Mitigation:** Support multiple key formats, robust parsing

### Risk 4: GPG Command Failures
**Mitigation:** Comprehensive error handling, graceful degradation

## Future Enhancements

1. **Key Trust Levels**
   - Differentiate between maintainer, contributor, reviewer keys
   - Support custom trust policies

2. **Signature Chain Validation**
   - Validate signature chains
   - Track key relationships

3. **Automated Key Updates**
   - Periodic keyring refresh
   - Automatic key import from repository

4. **Validation Dashboard**
   - Web UI for validation status
   - Trends and statistics
   - Alerting for unsigned/invalid signatures

---

## References

- Bitcoin Core Maintainer Keys: `contrib/builder-keys/`
- GPG Documentation: https://www.gnupg.org/documentation/
- Neo4j Schema: `backend/app/schema_design.md`
- Current Implementation: `backend/app/signature_extractor.py`

---

**Document Status:** Draft for Review  
**Next Action:** Begin implementation after harden_deploy merge
