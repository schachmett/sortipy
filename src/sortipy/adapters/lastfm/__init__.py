"""Public interface for the Last.fm adapter."""

from __future__ import annotations

from .client import should_cache_recent_tracks
from .fetcher import fetch_play_events

__all__ = [
    "fetch_play_events",
    "should_cache_recent_tracks",
]
