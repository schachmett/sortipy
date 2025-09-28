# Story DF3 – Enrich Library with External Metadata

**As a** data-curious listener  
**I want** each album and artist enriched with MusicBrainz/RateYourMusic metadata  
**So that** advanced filtering (genres, ratings, release details) is available in the UI.

## Acceptance Criteria
- Albums are matched to MusicBrainz entries via MBID or fuzzy lookup fallback.
- Genre tags, release country/label, and release type are captured from MusicBrainz.
- RateYourMusic ratings (or placeholders) are associated when the album is matched.
- Metadata refresh strategy is documented (frequency, cache invalidation).
