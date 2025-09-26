# ADR 0002: Canonical Domain Model for Library Entities

- Status: Proposed
- Date: 2025-03-05

## Context
External providers expose different shapes: Spotify centers on albums with track lists; Last.fm scrobbles are track-centric with implicit album relations; future metadata sources add yet more variants. We need a stable domain representation that supports cross-source analytics (album counts, artist trends, etc.).

## Decision
Define canonical domain entities: `Artist`, `Album`, `Track`, and `Scrobble`. Each captures provider-agnostic attributes and aggregates provider-specific metadata via separate value objects (e.g., `SpotifyAlbumData`, `LastFmTrackData`). Domain services maintain relationships (Artist 1:N Album, Album 1:N Track, Track 1:N Scrobble). Aggregations such as artist scrobble totals are implemented in repositories/use cases using prepared queries or materialized views to keep operations efficient.

## Consequences
- Domain logic reasons about a consistent model regardless of source.
- Requires translation layers inside adapters to map provider payloads to canonical entities.
- Aggregations (e.g., artist scrobble counts) must be optimized at the persistence layer, potentially via SQL views or cached summaries.
