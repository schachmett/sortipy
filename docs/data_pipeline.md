# Data Pipeline

This document describes the live ingestion architecture after the reconciliation cutover.

## Current Flow

All provider workflows follow the same shape:

1. Fetch provider data through an adapter.
2. Translate provider payloads into fresh domain aggregates.
3. Convert those aggregates into a catalog claim graph.
4. Run the reconciliation engine:
   - normalize
   - deduplicate
   - resolve
   - decide
   - apply
   - persist
5. Rebind user-owned activity objects to the materialized canonical catalog entities.
6. Persist user-owned activity objects and commit.

The reconciliation engine is catalog-focused. It owns `Artist`, `Label`, `ReleaseSet`, `Release`, `Recording`, contribution associations, `ReleaseTrack`, and catalog links. It does not resolve `User`, `LibraryItem`, or `PlayEvent` generically.

## Source Workflows

### Last.fm

- Adapter fetches play events.
- Translator produces fresh catalog aggregates referenced by those events.
- Workflow filters already-stored events using the play-event repository.
- The catalog subgraphs are reconciled.
- Each `PlayEvent` is rebound to the canonical `Recording` and, when available, the canonical `ReleaseTrack`.
- The workflow persists only the new events.

### Spotify

- Adapter fetches saved tracks, albums, and followed artists.
- Translator produces fresh target entities plus `LibraryItem` objects.
- The catalog targets are reconciled.
- Each `LibraryItem` is rebound to the canonical target entity.
- Duplicate library items are skipped with repository-level existence checks on `(user_id, target_type, target_id)`.

### MusicBrainz

- Candidate releases are selected from local catalog entities.
- Adapter fetches a fresh MusicBrainz release graph for each chosen candidate.
- The fetched graph is translated into a fresh `Release` aggregate.
- Reconciliation runs stagewise so the workflow can enforce an anchor check before apply/persist.
- If the root release claim does not resolve back to the targeted local release, the fetched graph is skipped and reported as manual review.

## Claim Graph Construction

`build_catalog_claim_graph(...)` traverses fresh catalog aggregates and emits:

- one entity claim per distinct in-memory catalog object
- association claims for `ReleaseSetContribution`, `RecordingContribution`, and `ReleaseTrack`
- link claims for `RELEASE_SET_RELEASE` and `RELEASE_LABEL`
- root claim ids used by source workflows

The builder also keeps object-to-claim mappings so workflows can translate original objects to representative claim ids after deduplication and then read the materialized canonical objects from `ApplyResult`.

## Persistence Model

Canonical entities are stored through SQLAlchemy repositories. Normalized keys are persisted in normalization sidecar rows so later runs can match by deterministic keys without mutating canonical entities.

User-owned entities remain workflow-owned:

- `PlayEvent` persistence is handled after catalog reconciliation
- `LibraryItem` persistence is handled after catalog reconciliation
- `User` loading and creation stay in the application layer

## Removed Legacy Path

The following modules are no longer part of the runtime architecture:

- `domain.ingest_pipeline`
- `domain.data_integration`
- `domain.entity_updates`
- `domain.enrichment`

Documentation and new code should refer to reconciliation workflows instead of sync or update pipelines.

## Current Gaps

- ADR-0007 provenance tables (`SourceIngest`, `RawPayload`) are not implemented yet.
- Canonical self-pointer infrastructure exists, but repository/query helpers still need broader canonicalized read support.
- Adapters still emit fresh domain aggregates first; direct claim-emitting adapters are a possible later simplification.
- Some SQLAlchemy workflows still emit autoflush warnings around user-owned activity attachment and should be cleaned up.
