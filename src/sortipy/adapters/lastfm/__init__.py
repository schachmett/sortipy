"""Public interface for the Last.fm adapter."""

from __future__ import annotations

from .client import LastFmAPIError, LastFmFetcher
from .schema import RecentTracksResponse, TrackPayload, TrackPayloadInput
from .translator import parse_play_event

__all__ = [
    "LastFmAPIError",
    "LastFmFetcher",
    "RecentTracksResponse",
    "TrackPayload",
    "TrackPayloadInput",
    "parse_play_event",
]
