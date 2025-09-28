from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

import pytest

from sortipy.adapters.lastfm import RecentTracksResponse

os.environ.setdefault("DATABASE_URI", "sqlite+pysqlite:///:memory:")


@pytest.fixture(scope="session")
def recent_tracks_payloads() -> tuple[RecentTracksResponse, ...]:
    path = Path(__file__).resolve().parent / "data" / "lastfm_recent_tracks.jsonl"
    with path.open() as handle:
        return tuple(cast(RecentTracksResponse, json.loads(line)) for line in handle)
