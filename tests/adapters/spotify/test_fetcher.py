"""Fetcher integration for Spotify adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sortipy.adapters.spotify.fetcher import fetch_library_items
from sortipy.domain.model import User

if TYPE_CHECKING:
    from sortipy.adapters.spotify.client import SpotifyClient
    from sortipy.config.spotify import SpotifyConfig


def test_fetch_library_items_combines_sources(
    spotipy_client: SpotifyClient, spotify_config: SpotifyConfig
) -> None:
    user = User(display_name="Spotify Smoke")
    result = fetch_library_items(
        client=spotipy_client,
        config=spotify_config,
        user=user,
        max_tracks=1,
        max_albums=1,
        max_artists=1,
    )
    items = list(result.library_items)

    assert len(items) == 3
    assert all(item.require_target() is not None for item in items)
