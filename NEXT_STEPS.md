# Core Explorer Kit - Next Steps

This document tracks the priorities and technical improvements planned for the project following the `harden_deploy` branch merge.

## 🚀 Immediate Priorities (Fast Follow)

### 1. PGP Signature Validation
Implement validation of extracted PGP signatures against a trusted maintainer keyring.
- **Requirements:** See [PGP_SIGNATURE_VALIDATION_REQUIREMENTS.md](PGP_SIGNATURE_VALIDATION_REQUIREMENTS.md)
- **Objective:** Enable auditing of signed vs. unsigned code in sensitive directories.

## 🛠️ Post-Merge Technical Improvements

### 2. Infrastructure & Logging
- **Migrate `print()` statements to `logging` module:** Transition from stdout prints to structured logging for better production observability and log management.
- **Code Cleanup:** Remove the "do we need this?" comment from the `uuid4()` function in `backend/app/neo4j_driver.py` (confirmed as used in `create_ingest_run`).

### 3. Data Integrity & Schema
- **Add `FileChange` uniqueness constraint:** Implement an explicit constraint in Neo4j to ensure data integrity for file-level changes.
  - *Query:* `CREATE CONSTRAINT filechange_unique IF NOT EXISTS FOR (fc:FileChange) REQUIRE (fc.commit_hash, fc.path) IS UNIQUE`
- **Implement Ingest Stage-Gating:** Ensure that advanced processing (Merges, Signatures) only runs if the commit backbone ingestion is verified as complete for the current `IngestRun`. This prevents partial data issues in `:MERGED_INCLUDES`.

## 🔮 Future Work (Lower Priority)

- **GitHub PR Integration:** Connect Pull Request data to the Git commit graph via the existing Event layer scaffolding.
- **Identity Resolution:** Implement "Person" clustering to link multiple Git identities to a single individual with confidence scores.
- **Deprecated Code Removal:** Create a dedicated branch to remove the `use_new_schema=False` code path and old `Actor` schema references once the transition is finalized.
