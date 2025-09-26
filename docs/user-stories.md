# User Stories

## Product Vision
Create an interactive, visual library explorer that blends your listening history (Last.fm) with your saved collections (Spotify) and rich metadata from third-party sources (MusicBrainz, RateYourMusic).

---

## Data Foundations

### Story DF1 – Ingest Last.fm Scrobbles
**As a** listener who scrobbles to Last.fm  
**I want** my scrobble history replicated into Sortipy’s persistence layer  
**So that** all downstream views can rely on an up-to-date play count per track and album.

**Acceptance Criteria**
- Environment configuration for Last.fm credentials is validated at startup.
- Recent scrobbles are fetched incrementally and stored without duplicates.
- Stored scrobbles retain timestamp, track, album, and artist associations.
- A rerun does not re-ingest the same scrobbles (idempotent sync).

### Story DF2 – Sync Spotify Saved Albums
**As a** Spotify user curating a saved-album library  
**I want** Sortipy to ingest and persist my saved albums  
**So that** I can analyze them alongside listening history and external metadata.

**Acceptance Criteria**
- OAuth flow for Spotify is handled and tokens stored securely.
- Saved albums are fetched in batches until the entire library (or configured limit) is synced.
- Each album record includes release date (with normalized precision), artists, and Spotify IDs.
- Sync can be rerun to pick up adds/removes without duplicating records.

### Story DF3 – Enrich Library with External Metadata
**As a** data-curious listener  
**I want** each album and artist enriched with MusicBrainz/RateYourMusic metadata  
**So that** advanced filtering (genres, ratings, release details) is available in the UI.

**Acceptance Criteria**
- Albums are matched to MusicBrainz entries via MBID or fuzzy lookup fallback.
- Genre tags, release country/label, and release type are captured from MusicBrainz.
- RateYourMusic ratings (or placeholders) are associated when the album is matched.
- Metadata refresh strategy is documented (frequency, cache invalidation).

---

## Analytics & Insights

### Story A1 – Albums by Decade with Scrobble Totals
**As a** listener exploring eras  
**I want** to filter my saved albums by decade and see cumulative scrobble counts  
**So that** I understand which decades dominate my listening.

**Acceptance Criteria**
- UI filter exposes decade buckets derived from release dates.
- Album list shows total scrobbles per album (from Last.fm sync).
- Sorting by scrobbles and by alphabetical order is available.
- Empty states clarify when no albums match a selected decade.

### Story A2 – Unplayed Saved Albums
**As a** collector of music  
**I want** to surface saved albums with zero scrobbles  
**So that** I can focus on unheard additions to my library.

**Acceptance Criteria**
- View lists Spotify-saved albums lacking any associated scrobbles.
- Albums with partial scrobbling (e.g., one track) are excluded from this view.
- The view supports sorting by date added and release date.
- There is an action or link to start playback or mark as listened.

### Story A3 – Genre-Focused Discovery
**As a** genre explorer  
**I want** to search by MusicBrainz/RYM genres and surface matching albums in my library  
**So that** I can deep dive into specific styles I enjoy.

**Acceptance Criteria**
- Genre taxonomy is deduplicated and presented via search/autocomplete.
- Selecting a genre filters albums where the tag matches (including multi-genre albums).
- Result list exposes key metadata: release date, scrobbles, external rating.
- Multiple genre selection (AND/OR) behavior is defined and implemented.

### Story A4 – Artist Release Timeline
**As a** fan of specific artists  
**I want** to view a timeline of albums I’ve listened to, ordered by release date  
**So that** I can spot gaps or trends in my engagement with that artist.

**Acceptance Criteria**
- Artist search presents distinct artists from the combined dataset.
- Selected artist view shows albums with release year, cover art, and scrobble counts.
- Timeline highlights albums with zero scrobbles differently from frequently played ones.
- Navigation lets me jump from an album to track-level details.

### Story A5 – Attribute-Driven Library Browser
**As a** power user  
**I want** a faceted browser across release date, external ratings, listening time, and album length  
**So that** I can slice my library with custom criteria.

**Acceptance Criteria**
- Filters exist for release date range, RYM rating thresholds, total listening minutes, and album duration.
- Adjusting filters updates results in real time without page reloads.
- Selected filters are displayed as removable chips/pills.
- Performance remains acceptable with full library (e.g., <200ms query response target).

### Story A6 – Album-to-Track View Toggle with Artwork
**As a** visual listener  
**I want** to browse albums with cover art but drill down into track-level stats  
**So that** I can appreciate artwork while exploring detailed listening patterns.

**Acceptance Criteria**
- Default view shows album cards with cover art, key metadata, and scrobble summary.
- Toggle expands a selected album into a track table (track number, duration, scrobbles).
- Track view includes quick navigation back to the album grid.
- High-resolution cover images are cached to avoid UI lag.

---

## Notes
- Stories are independent slices; each references data foundation stories DF1–DF3 where relevant.
- When moving to a formal tracker, copy each story with its label (DFx/Ax) to keep traceability.
- Add supporting technical tasks as needed (ETL scheduling, caching, API quotas) while keeping user-facing stories clean.
