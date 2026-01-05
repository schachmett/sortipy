"""Fetcher integration for Spotify adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sortipy.adapters.spotify.fetcher import fetch_library_items
from sortipy.domain.model import User

if TYPE_CHECKING:
    from sortipy.adapters.spotify.client import SpotifyClient


def test_fetch_library_items_combines_sources(spotipy_client: SpotifyClient) -> None:
    user = User(display_name="Spotify Smoke")
    result = fetch_library_items(
        client=spotipy_client,
        user=user,
        max_tracks=1,
        max_albums=1,
        max_artists=1,
    )
    items = list(result.library_items)

    assert len(items) == 3
    assert all(item.require_target() is not None for item in items)
