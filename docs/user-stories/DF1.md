# Story DF1 – Ingest Last.fm Scrobbles

**As a** listener who scrobbles to Last.fm  
**I want** my scrobble history replicated into Sortipy’s persistence layer  
**So that** all downstream views can rely on an up-to-date play count per track and album.

## Acceptance Criteria
- Environment configuration for Last.fm credentials is validated at startup, and missing or blank values produce a clear failure before any sync attempt.
- Recent scrobbles are fetched incrementally and stored without duplicates.
- Stored scrobbles retain timestamp, track, album, and artist associations.
- A rerun does not re-ingest the same scrobbles (idempotent sync).
