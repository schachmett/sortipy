# Sortipy

Sortipy is a music-library integration project built around a canonical domain model and a reconciliation pipeline. Last.fm play events, Spotify library items, and MusicBrainz release metadata are translated into fresh domain graphs, reconciled against the stored catalog, and then persisted through SQLAlchemy adapters.

## Current Status

The live ingestion path is reconciliation-only:

- Last.fm play events: `reconcile lastfm`
- Spotify library items: `reconcile spotify-library`
- MusicBrainz release updates: `reconcile musicbrainz-releases`

Legacy domain packages such as `ingest_pipeline`, `data_integration`, `entity_updates`, and `domain.enrichment` have been removed.

## Requirements

- Python 3.14+
- `uv`
- Spotify credentials for Spotify workflows
- Last.fm credentials for Last.fm workflows
- A writable SQLite or other SQLAlchemy-supported database

## Setup

1. Install dependencies:

```sh
uv sync --group dev
```

2. Create `.env` in the project root:

```sh
SPOTIPY_CLIENT_ID=<spotify-client-id>
SPOTIPY_CLIENT_SECRET=<spotify-client-secret>
SPOTIPY_REDIRECT_URI=http://127.0.0.1:9090
LASTFM_API_KEY=<lastfm-api-key>
LASTFM_USER_NAME=<lastfm-user-name>
# Optional
# DATABASE_URI=sqlite+pysqlite:///absolute/path/to/sortipy.db
# SORTIPY_DATA_DIR=/absolute/path/to/data-dir
```

3. Create a user:

```sh
uv run sortipy user create --display-name "Example User" --lastfm-user demo --spotify-user-id demo
```

## CLI

Run the CLI through the project script:

```sh
uv run sortipy --help
```

Examples:

```sh
uv run sortipy reconcile lastfm --user-id <uuid> --lookback-hours 24
uv run sortipy reconcile spotify-library --user-id <uuid>
uv run sortipy reconcile musicbrainz-releases --limit 25
```

## Architecture

Sortipy follows ports-and-adapters boundaries:

- domain model: canonical music entities plus user-owned activity entities
- adapters: Last.fm, Spotify, MusicBrainz, SQLAlchemy
- reconciliation core: normalize, deduplicate, resolve, decide, apply, persist
- workflows: source-specific orchestration that fetches provider data, builds claim graphs, runs reconciliation, then rebinds `PlayEvent` and `LibraryItem` objects to canonical catalog entities

Start with these docs:

- `docs/adr/0001-architecture-style.md`
- `docs/adr/0002-domain-model.md`
- `docs/adr/0003-persistence-mapping.md`
- `docs/adr/0004-ingestion-strategy.md`
- `docs/data_pipeline.md`
- `docs/todo.md`

## Development

Common quality gates:

```sh
uv run poe fix
uv run poe lint
uv run poe typecheck
uv run poe test
```

Automation-specific workflow notes live in `AGENTS.md`.
