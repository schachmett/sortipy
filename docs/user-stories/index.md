# User Stories

## Product Vision
Create an interactive, visual library explorer that blends your listening history (Last.fm) with your saved collections (Spotify) and rich metadata from third-party sources (MusicBrainz, RateYourMusic).

## Data Foundations
- [DF1 – Ingest Last.fm Scrobbles](./DF1.md)
- [DF2 – Sync Spotify Saved Albums](./DF2.md)
- [DF3 – Enrich Library with External Metadata](./DF3.md)

## Analytics & Insights
- [A1 – Albums by Decade with Scrobble Totals](./A1.md)
- [A2 – Unplayed Saved Albums](./A2.md)
- [A3 – Genre-Focused Discovery](./A3.md)
- [A4 – Artist Release Timeline](./A4.md)
- [A5 – Attribute-Driven Library Browser](./A5.md)
- [A6 – Album-to-Track View Toggle with Artwork](./A6.md)

## Notes
- Stories are independent slices; each references data foundation stories DF1–DF3 where relevant.
- When moving to a formal tracker, copy each story with its label (DFx/Ax) to keep traceability.
- Add supporting technical tasks as needed (ETL scheduling, caching, API quotas) while keeping user-facing stories clean.
