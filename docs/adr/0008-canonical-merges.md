# ADR 0008: Canonical Merges via Self-Pointer

- Status: Accepted
- Date: 2025-10-17

## Context
Multiple data sources can produce duplicate representations of the same real-world entity (e.g., “The National” from Last.fm and Spotify). We need a deduplication strategy that is repeatable, auditable, and reversible without rewriting foreign keys across the database. The domain already references entities by ID; we want merges to be lightweight yet safe, even as we add automated heuristics.

## Implementation Status

As of March 7, 2026, this ADR is partially implemented.

- Mergeable entities expose `canonical_id`/`resolved_id` behavior in the domain model.
- SQLAlchemy mappings and migrations include canonical self-pointers and `EntityMerge`.
- The reconciliation engine uses resolved entity identity while merging and rebinding graphs.
- Repository/query helpers do not yet provide a complete canonicalized read layer across the whole application, so some callers can still observe pre-coalesced records unless they resolve canonicals explicitly.

## Decision
Adopt the **canonical pointer** pattern for mergeable entities (Artist, ReleaseSet, Release, Recording, Track, User). Each table gains a nullable `canonical_id` self-foreign key defaulting to its own primary key. External identifiers reside in the shared `ExternalID` table, so merge heuristics start by searching for overlapping namespaces/values before falling back to other attributes. Merging duplicate records consists of:

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
- External identifier collisions are the primary signal for automated merges. To keep performance predictable, we maintain indexes on `(namespace, value, entity_type)` in the `ExternalID` table and rely on repository helpers to consolidate IDs when two records are merged.

## Adjacent ADRs
- ADR 0002 (Domain Model) – the canonical entities that receive these merge pointers.
