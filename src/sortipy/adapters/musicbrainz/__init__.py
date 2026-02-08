"""MusicBrainz enrichment adapter."""

from __future__ import annotations

from .fetcher import (
    fetch_release_candidates_from_artist,
    fetch_release_candidates_from_recording,
    fetch_release_candidates_from_release_set,
    fetch_release_update,
)

__all__ = [
    "fetch_release_candidates_from_artist",
    "fetch_release_candidates_from_recording",
    "fetch_release_candidates_from_release_set",
    "fetch_release_update",
]
