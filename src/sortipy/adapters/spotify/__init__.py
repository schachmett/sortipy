"""Spotify adapter package."""

from __future__ import annotations

from .client import SpotifyClient
from .fetcher import fetch_library_items
from .schema import (
    SavedAlbumItem,
    SavedTrackItem,
    SpotifyAlbum,
    SpotifyArtist,
    SpotifyTrack,
)
from .translator import (
    translate_followed_artist,
    translate_saved_album,
    translate_saved_track,
)

__all__ = [
    "SavedAlbumItem",
    "SavedTrackItem",
    "SpotifyAlbum",
    "SpotifyArtist",
    "SpotifyClient",
    "SpotifyTrack",
    "fetch_library_items",
    "translate_followed_artist",
    "translate_saved_album",
    "translate_saved_track",
]
