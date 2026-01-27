"""MusicBrainz enrichment adapter."""

from __future__ import annotations

from .fetcher import enrich_recordings

__all__ = [
    "enrich_recordings",
]
