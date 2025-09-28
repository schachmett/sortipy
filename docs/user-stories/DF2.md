# Story DF2 – Sync Spotify Saved Albums

**As a** Spotify user curating a saved-album library  
**I want** Sortipy to ingest and persist my saved albums  
**So that** I can analyze them alongside listening history and external metadata.

## Acceptance Criteria
- OAuth flow for Spotify is handled and tokens stored securely.
- Saved albums are fetched in batches until the entire library (or configured limit) is synced.
- Each album record includes release date (with normalized precision), artists, and Spotify IDs.
- Sync can be rerun to pick up adds/removes without duplicating records.
