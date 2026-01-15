"""Public interface for the Last.fm adapter."""

from __future__ import annotations

from .client import LastFmAPIError, LastFmClient
from .fetcher import fetch_play_events
from .schema import RecentTracksResponse, TrackPayload, TrackPayloadInput
from .translator import parse_play_event

__all__ = [
    "LastFmAPIError",
    "LastFmClient",
    "RecentTracksResponse",
    "TrackPayload",
    "TrackPayloadInput",
    "fetch_play_events",
    "parse_play_event",
]
