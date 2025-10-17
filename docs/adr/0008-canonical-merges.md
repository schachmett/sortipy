# ADR 0008: Canonical Merges via Self-Pointer

- Status: Proposed
- Date: 2025-10-17

## Context
Multiple data sources can produce duplicate representations of the same real-world entity (e.g., “The National” from Last.fm and Spotify). We need a deduplication strategy that is repeatable, auditable, and reversible without rewriting foreign keys across the database. The domain already references entities by ID; we want merges to be lightweight yet safe, even as we add automated heuristics.

## Decision
Adopt the **canonical pointer** pattern for mergeable entities (Artist, ReleaseSet, Release, Recording, Track, User). Each table gains a nullable `canonical_id` self-foreign key defaulting to its own primary key. Merging duplicate records consists of:

1. Setting the duplicate entity’s `canonical_id = target_id`.
2. Recording an `EntityMerge` row with `source_id`, `target_id`, reason, actor, and timestamp.

Consumers resolve the canonical entity by coalescing `canonical_id` with the primary key (e.g., `COALESCE(entity.canonical_id, entity.id)`). Repository and query helpers encapsulate this resolution so callers do not forget it. Merges are reversible by resetting `canonical_id` and recording an inverse merge entry.

## Consequences
- **Pros**:
  - Merges are O(1) updates with full audit history and easy rollbacks.
  - No cascade updates are required; foreign keys on child tables remain untouched.
  - Automated heuristics can propose merges without risking unrecoverable data loss.
- **Cons / Mitigations**:
  - Every query that needs a deduplicated view must resolve `canonical_id`. To avoid mistakes, repositories must expose helper methods or SQL views that always coalesce canonical IDs; indexes on `canonical_id` keep joins efficient.
  - Long-running analytics must factor in canonical resolution; we mitigate by providing canonicalized materialized views for heavy workloads when needed.
  - If an entity is hard-deleted, merges referencing it remain for audit; we must document cleanup procedures or soft-delete policies.

## Adjacent ADRs
- ADR 0002 (Domain Model) – the canonical entities that receive these merge pointers.
- ADR 0007 (Data Provenance) – raw payload and checkpoint information used to justify/inspect merges.
