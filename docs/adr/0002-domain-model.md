# ADR 0002: Canonical Domain Model for Library Entities

- Status: Proposed
- Date: 2025-10-17

## Context
External providers expose different shapes: Spotify centers on albums with track lists; Last.fm scrobbles are track-centric with implicit album relations; MusicBrainz describes releases and recordings; other sources add ratings, genres, and audio analysis. We need a stable domain representation that supports cross-source analytics (album counts, artist trends, play history) while staying vendor-neutral and extensible.

## Decision
Adopt a canonical domain model inspired by MusicBrainz terminology but expressed in project-agnostic names. The core entities are:

- **Artist** – performers, composers, producers, etc. Fields include name, sort_name, country, and optional formation/disbandment dates.
- **ReleaseSet** – the abstract concept of a release (studio album, EP, live set). Tracks high-level metadata such as title, primary type, and first release year.
- **Release** – a concrete manifestation of a ReleaseSet (regional pressing, deluxe edition, digital reissue). Fields include release date, country, label, catalog number, barcode, etc.
- **Recording** – a specific performance/mix of a composition. Includes duration, ISRC, version/mix hints.
- **Track** – the placement of a Recording on a particular Release (disc number, track number, title overrides, track-level duration).
- **PlayEvent** – a user listening event/scrobble tying back to the Recording (and optionally the Track) with timestamp and source information.
- **User** – local representation of a listener with links to external account identifiers.
- **ExternalID** – a generic mapping of any entity to provider-specific identifiers (Spotify IDs, MusicBrainz IDs, ISRC, etc.). Selected hot-path identifiers may be cached on the entity for convenience, but ExternalID remains the source of truth.
- **LibraryItem** – user “saved” relationships (saved artists, releases, recordings) recording the origin (Spotify, manual, etc.).

Association tables that carry additional semantics include:

- **ReleaseSetArtist** – m:n between ReleaseSet and Artist with role and position (primary artist, featured, producer, etc.).
- **RecordingArtist** – m:n between Recording and Artist with rich role metadata (instrument, guest vocals, remix…).
- **UserLibraryItem** – user/library relationship with origin timestamps and source tags.

Provider metadata is stored externally. External IDs live primarily in the ExternalID table; only frequently used IDs may be duplicated on the entity for performance. Tertiary enrichment (audio features, ratings, artwork) resides in dedicated enrichment tables to keep the core model lean.

## Rationale
- Separating ReleaseSet/Release/Recording mirrors industry and MusicBrainz realities, enabling accurate deduplication across variants.
- Tracks represent the manifestation of a Recording on a specific Release, allowing multiple Releases (deluxe, vinyl, compilation) to reference the same Recording data.
- PlayEvent references the Recording and optionally Track so analytics can roll up by composition/performance regardless of Release variants.
- ExternalID keeps the model vendor-independent while still allowing direct lookups by external identifiers.
- Keeping enrichment (audio features, ratings) outside the core domain avoids polluting core entities with provider-specific attributes.

## Consequences
- Adapter layers must map provider payloads into the canonical hierarchy (e.g., Last.fm scrobbles → Recording + PlayEvent, Spotify album → ReleaseSet + Release + Tracks).
- SQLAlchemy mappings will need to model one-to-many (Artist ↔ ReleaseSet, ReleaseSet ↔ Releases, Release ↔ Tracks) and many-to-many relationships (ReleaseSetArtist, RecordingArtist) explicitly.
- External metadata retrieval (MusicBrainz, Discogs, etc.) will populate ReleaseSet/Release/Recording structures; user-facing ingests (Spotify saved albums, Last.fm plays) can slot into the same model without schema changes.
- External metadata retrieval (MusicBrainz, Discogs, etc.) will populate ReleaseSet/Release/Recording structures; user-facing ingests (Spotify saved albums, Last.fm plays) can slot into the same model without schema changes.

## Future Work / Open Questions
- Introduce **Work** entities (composition-level) once needed, adding an optional `work_id` to Recordings.
- Define richer `RecordingArtist`/`ReleaseSetArtist` role vocabularies and reference data.
- Explore caching of frequently used external IDs on entities (e.g., `spotify_release_id`) and index requirements.

## Adjacent ADRs
- Canonical merge behavior (self-referencing canonical IDs, audit trail) – documented separately.
- Raw data provenance and ingestion batch tracking – documented separately.
