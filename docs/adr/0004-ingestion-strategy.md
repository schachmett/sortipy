# ADR 0004: Layered Ingestion Strategy

- Status: Proposed
- Date: 2025-10-17

## Context
Sortipy ingests data from heterogeneous sources with different fidelity: user-facing services (Spotify, Last.fm), canonical metadata catalogues (MusicBrainz, Discogs), and tertiary enrichments (ratings, audio analysis, artwork). We need an ingestion approach that lets us ship quickly with user data while leaving room to enrich the canonical model later—without rewriting the pipeline each time. Scheduling remains simple (pull-based jobs) in the early stages, but the architectural layers must survive as we evolve toward event-driven or batch ETL processes.

## Decision
Adopt a **three-layer ingestion pipeline**:

1. **Primary (user-centric) layer** – imports data owned or curated by the user (Spotify saved albums, Last.fm play events, manual library edits). Jobs focus on idempotent upserts plus checkpointing (see ADR 0007).
2. **Reference (canonical) layer** – enriches entities with authoritative catalogues (MusicBrainz to resolve ReleaseSets/Releases/Recordings, Discogs for label/catalog data). Runs after primary ingestion, matching and linking to canonical IDs without overwriting user-sourced facts.
3. **Enrichment (tertiary) layer** – augments canonical entities with optional metadata such as ratings (RateYourMusic), audio features (Spotify analysis), artwork, or fan statistics. These enrichment jobs can execute independently once primary and reference layers have established the canonical keys.

Each layer operates through explicit ports/adapters and produces outputs that downstream layers can consume. Initial scheduling remains on-demand/pull (e.g., CLI or cron), but the ports are designed so future event-driven ingestion can drop in without domain changes.

## Consequences
- Early development stays simple (pull-based jobs), while the layered approach provides a roadmap for progressive enrichment.
- Each layer has clear responsibilities: user trust and freshness in the primary layer, correctness and canonical alignment in the reference layer, optional insights in the enrichment layer.
- Requires careful coordination and matching between layers (e.g., reconciling primary ingest data with MusicBrainz identifiers).
- When we introduce new data types, we can place them in the appropriate layer without disturbing existing flows.
- Checkpointing and raw payload persistence are defined in the data provenance ADR.
- Event-driven or streaming ingestion can later replace the pull jobs per layer without altering domain services.

## Adjacent ADRs
- Canonical merge behavior – covers self-referencing merges and dedupe auditing (ADR TBD).
- Data provenance & raw payload storage – see ADR 0007.
