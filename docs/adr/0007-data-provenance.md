# ADR 0007: Raw Data Provenance & Checkpointing

- Status: Proposed
- Date: 2025-10-17

## Context
Ingested data comes from multiple providers and layers (primary user data, reference catalogues, tertiary enrichments). To debug, re-run ingests, and guarantee idempotency we need to persist raw payloads and checkpoints independently of the canonical domain tables. This provenance layer must be shared across ingestion jobs so that reconciliation and auditing are consistent.

## Decision
Introduce a dedicated provenance schema consisting of:

- **SourceIngest** records – one row per ingestion run (per source and job) capturing timestamps, parameters, cursor/checkpoint values, success status, and linkage to the user initiating the run. Each job stores the canonical cursor (e.g., Last.fm `from` timestamp, Spotify saved snapshot cursor) so the next run can resume without gaps or duplicates.
- **RawPayload** tables – per high-volume entity class (e.g., `raw_play_event`, `raw_release`, `raw_library_item`). Each payload row stores the `source_ingest_id`, external identifiers, hash/dedup keys, the raw JSON payload, and optional parsed projections (e.g., artist name, timestamp). These tables support reprocessing and matching diagnostics.
- **Linkage columns on canonical entities** – canonical tables may store a foreign key to the originating `raw_*` row for ease of traceability, but canonical updates never rely on raw tables at query time.

Access patterns:

- Ingest jobs *first* read their last successful `SourceIngest` checkpoint, fetch new data, persist raw payload rows, then transform into canonical entities.
- Deduplication uses raw hashes/external IDs before canonical merges, ensuring we can reason about duplicates even if canonical relations change later.
- Reprocessing a batch (backfill or enrichment) creates a new `SourceIngest` record, keeping historical provenance immutable.

Retention:

- Raw payload tables are retained indefinitely during early development. Once volumes grow, we can configure retention windows per source (e.g., keep 90 days of play events) with snapshot exports for archival.

## Consequences
- All ingestion jobs share a consistent checkpoint mechanism; retries and backfills reference `SourceIngest` instead of ad-hoc cursors.
- Debugging is easier: canonical anomalies can be traced back to the exact raw payload and ingest run.
- Storage requirements increase (raw JSON + hashes), so retention policies must be monitored as libraries grow.
- Schema migrations for provenance tables are versioned through Alembic alongside canonical tables (see ADR 0003).

## Adjacent ADRs
- ADR 0002 (Domain Model) – describes the canonical entities that consume transformed data.
- ADR 0004 (Ingestion Strategy) – defines the layered ingestion approach that relies on this provenance schema.
- ADR TBD (Canonical Merge Behaviour) – explains how canonical entities deduplicate after raw payload processing.
