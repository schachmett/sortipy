# Sortipy

Sortipy is an experimental music library explorer. It combines your Spotify saved albums, Last.fm scrobbles, and third-party metadata (MusicBrainz/RateYourMusic planned) to surface insights about what you listen to and what you are missing.

## Project Goals
- Keep a canonical domain model for artists, albums, tracks, and scrobbles independent of external APIs.
- Provide sync pipelines for Spotify, Last.fm, and metadata providers.
- Deliver analytics such as decade views, unheard albums, genre exploration, and artist timelines.
- Start with a CLI adapter, paving the way for richer visualizations later.

The high level plan and user-facing stories live under `docs/user-stories/` (start with `docs/user-stories/index.md`). Architectural decisions are tracked under `docs/adr/`.

## Architecture
Sortipy follows a ports-and-adapters (hexagonal) style:
- **Domain services** expose use cases and work with canonical entities.
- **Secondary adapters** handle data access (Spotify, Last.fm, MusicBrainz/RYM, SQL persistence) by implementing domain-defined ports.
- **Primary adapters** drive the domain; currently this is a CLI entry point (`src/sortipy/main.py`).

See the ADRs for the detailed rationale and constraints.

## Status
Work is focused on the data foundation stories: reliable ingestion of Last.fm scrobbles, syncing Spotify saved albums, and enriching records with external metadata. UI and advanced analytics are planned next.

## Prerequisites
- Python 3.12+
- Spotify developer application with OAuth credentials
- Last.fm API key and username
- Optional: a custom database URI (SQLite recommended) or a data directory override

## Setup
1. Clone the repository and `cd` into it.
2. (Optional) Create a virtual environment and activate it:
   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```sh
   python3 -m pip install -e .
   ```
4. Create a `.env` file in the project root with the required variables:
   ```sh
   SPOTIPY_CLIENT_ID=<spotify-client-id>
   SPOTIPY_CLIENT_SECRET=<spotify-client-secret>
   SPOTIPY_REDIRECT_URI=http://127.0.0.1:9090
   LASTFM_API_KEY=<lastfm-api-key>
   LASTFM_USER_NAME=<lastfm-username>
   # Optional overrides
   # DATABASE_URI=sqlite+pysqlite:///absolute/path/to/sortipy.db
   # SORTIPY_DATA_DIR=/absolute/path/to/data-directory
   ```

## Running the CLI prototype
```sh
python3 src/sortipy/main.py
```
The current entry point performs a proof-of-concept Last.fm sync into the configured database. As domain services mature, new commands and outputs will be added.

## Contributing
- Review `docs/user-stories/index.md` to understand the planned features.
- Read `AGENTS.md` for automation workflow expectations and links to the key policies.
- Follow the testing guidance in `docs/policies/testing.md` and the architectural decisions in `docs/adr/`.
- Use the tooling configured in `pyproject.toml` (or `pre-commit run --all-files`) before submitting changes.

## License
MIT License. See `LICENSE` for details.
