# Data Pipeline Overview — Sortipy Entity Normalization & Canonicalization

This document describes the complete data ingestion and deduplication pipeline in **Sortipy**, including all steps from source ingestion to canonical persistence.  
It is written as developer-facing documentation for the LLM assistant (Codex) and future contributors.

---

## 0. Overview

The pipeline transforms raw source data (e.g. from **Last.fm**, **MusicBrainz**, or other APIs) into normalized and deduplicated **domain entities** (`Artist`, `ReleaseSet`, `Release`, `Recording`, `Track`, `PlayEvent`), and persists them in the database while merging them with previously known entities.

All operations are split into two major phases:

1. **Normalization**  
   → Purely in-memory, source-specific cleaning and intra-batch deduplication.

2. **Canonicalization**  
   → Database-backed reconciliation of the normalized entities with the persistent canonical data.

A **SQLAlchemy Session** acts as the built-in **Identity Map** and **Unit of Work** — no custom cache layer is needed.

---

## 1. Fetch Phase (Source Adapters)

### Goal
Transform raw API data into domain entities and build an in-memory graph.

### Steps
1. Retrieve data from the external provider (e.g., Last.fm JSON).
2. For each item (e.g. a play event):
   - Parse all referenced entities:
     ```python
     artist, release_set, release, recording, track = _parse_entities(track_payload)
     ```
   - Build the relationships:
     ```python
     event = PlayEvent(
         played_at=played_at,
         source=Provider.LASTFM,
         recording=recording,
         track=track,
     )
     recording.play_events.append(event)
     track.play_events.append(event)
     artist.recordings.append(recording)
     artist.release_sets.append(release_set)
     ```
3. Collect all entities in an **in-memory ingest graph**.

No database access happens in this phase.

---

## 2. Normalization Phase

### Goal
Prepare entities for comparison and deduplication:
- Normalize all string and numeric fields.
- Compute deterministic keys.
- Perform intra-ingest deduplication (collapse duplicates within the same batch).

### 2.1 Field Normalization

For every entity type:

| Entity   | Normalized Fields             | Example Transformation |
|-----------|------------------------------|------------------------|
| Artist    | `normalized_name`            | Unicode NFKC, `.casefold()`, strip punctuation |
| Recording | `normalized_title`, `duration_bin` | Bucket duration (e.g. `duration_ms // 2000`) |
| Release   | `normalized_title`, `normalized_artist_name` | lowercased, whitespace-collapsed |

These normalized values are stored in a dedicated normalization state (sidecar) so later
phases can consume them without mutating the canonical entities. They feed deterministic
key calculations and later canonicalization.

### 2.2 Deterministic Keys

Each entity defines a *priority-ordered* list of deterministic keys, combining the relevant
fields for equality:

| Entity | Deterministic Key Example |
|---------|---------------------------|
| Artist | `(source, normalized_name, musicbrainz_id or None)` |
| Recording | `(artist.normalized_name, normalized_title, duration_bin)` |
| Release | `(artist.normalized_name, normalized_title)` |

Persist these priority key tuples inside the normalization state so deduplication and
canonicalization can try the strongest match first (e.g., MusicBrainz IDs) and fall back to
normalized-field keys when richer metadata is unavailable.

### 2.3 Intra-Ingest Deduplication

#### Goal
Collapse duplicate entities **within the same ingest batch** — e.g., multiple `Artist("Radiohead")` from Last.fm.

#### Algorithm
For each entity type (Artist, Recording, Release, …):

1. Initialize an empty dict:  
   `entities_by_key: dict[key, Entity] = {}`
2. Iterate through all entities:
   1. **Fetch keys** → `keys = normalization_state.priority_keys_for(entity)`
   2. Try each key in order until one matches or all are exhausted:
      - If key not found: store `entities_by_key[key] = entity` and stop checking keys.
      - Else:
        - Merge duplicate into the primary entity using **merge policy**:
          - Prefer non-`None` values.
          - Ignore capitalization and whitespace differences.
          - Log a warning for conflicting non-trivial differences.
        - **Rewire references** from duplicate → primary:
          - Update all related objects that referenced the duplicate.
          - Example: `recording.artist`, `artist.recordings`, `artist.release_sets`.
        - Stop checking remaining keys because the duplicate has been resolved.
3. After iteration, replace all duplicates in the ingest graph with the canonical instance.

**Result:**  
A clean, minimal ingest graph — all obvious duplicates merged, all fields normalized, and deterministic keys assigned.

---

## 3. Canonicalization Phase

### Goal
Match normalized in-memory entities against the persistent database, merge where applicable, and persist new or updated entities.

### Key Principle
Use a single **SQLAlchemy Session** per batch run.  
The Session automatically maintains identity consistency (acts as an Identity Map).

### Typical Flow
```python
with UnitOfWork(session_factory) as uow:
    canonicalize_batch(ingest_graph, uow)
```

---

## 4. Canonicalization Logic (Per Entity Type)

Canonicalization proceeds in topological order:

1. `Artist`
2. `Label`
3. `ReleaseSet`
4. `Release`
5. `Recording`
6. `Track`
7. `PlayEvent`

Each entity is resolved and merged before dependent entities (e.g., `Recording` after `Artist`).

### 4.1 Lookup Stages

1. **External ID Lookup**

   * `repo.get_by_external_id(source, id_value)`
   * Returns an existing entity if a known external ID matches.
   * If multiple IDs conflict → log conflict, treat as unmatched.

2. **Deterministic Key Lookup**

   * `repo.find_by_deterministic_key(key)`
   * Typically `WHERE normalized_name = ?` (and possibly `artist_id`, `duration_bin`, etc.)
   * If one match → accept.
     If multiple → ambiguous → optional fuzzy stage.

3. **Fuzzy Matching (optional, conservative)**

   * `repo.find_candidates_for_fuzzy(...)` performs coarse SQL filtering:

     ```sql
     WHERE normalized_title LIKE ? AND duration_bin BETWEEN ? AND ?
     ```
   * Use `rapidfuzz` in Python to compare normalized strings.
   * If similarity > threshold (e.g., 95%) → accept, else log as conflict.

---

### 4.2 Merge Policy (Existing Entity Found)

| Case                                   | Action                                     |
| -------------------------------------- | ------------------------------------------ |
| `new is None`                          | keep existing                              |
| `old is None`                          | take new                                   |
| normalized(`old`) == normalized(`new`) | ignore                                     |
| both non-None and differ               | log conflict, optionally prefer `existing` |

Additionally:

* Merge all new external IDs into the existing entity.
* Keep track of all merged sources (for provenance/audit if needed).

---

### 4.3 New Entity Creation

If no match found:

```python
uow.artists.add(artist)
```

* The Session tracks it automatically (IdentityMap + UnitOfWork semantics).

---

### 4.4 Graph Rewriting

After all canonical lookups:

1. For every entity, store mapping:
   `ingest_entity → canonical_entity`
2. Walk the ingest graph:

   * Replace all references with their canonical counterparts:

     ```python
     recording.artist = artist_mapping[recording.artist]
     play_event.recording = rec_mapping[play_event.recording]
     play_event.track = track_mapping.get(play_event.track, play_event.track)
     ```

After this step, the full ingest graph references only canonical (DB-backed) entities.

---

## 5. Persistence

At the end of the UnitOfWork:

1. If no exception:

   ```python
   uow.session.commit()
   ```

   * Inserts new entities and updates merged ones.
2. On error:

   ```python
   uow.session.rollback()
   ```
3. Close the session.

---

## 6. Summary of Responsibilities

| Phase              | Responsibilities                        | DB Access | Data Scope       |
| ------------------ | --------------------------------------- | --------- | ---------------- |
| Fetch              | Source parsing, graph building          | ❌         | per ingest batch |
| Normalization      | Field normalization, deterministic keys | ❌         | per ingest batch |
| Intra-Ingest Dedup | Collapse duplicates inside batch        | ❌         | per ingest batch |
| Canonicalization   | Match & merge with persistent DB        | ✅         | batch + DB       |
| Persistence        | Commit all new/merged entities          | ✅         | canonical DB     |

---

## 7. Notes for Codex (LLM Integration)

When Codex works on this codebase:

* Always fetch all **relevant source files** before reasoning:
  * `src/sortipy/domain/model/` (entity definitions)
  * `src/sortipy/domain/ports/` (ports for persistence, unit of work and data fetching)
  * `src/sortipy/adapters/sqlalchemy/` (implementation for persistence and uow ports)
  * `src/sortipy/adapters/lastfm/` (implementation for fetcher port)
  * `AGENTS.md` (project orchestration rules)
* Assume the SQLAlchemy Session provides the Identity Map.
* Do **not** design a custom cache for PKs.
* Focus instead on:
  * Deterministic key consistency across normalization + canonicalization.
  * Declarative merge policies per entity type.
  * Clean orchestration between phases.
