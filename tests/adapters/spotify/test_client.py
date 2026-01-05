"""Client iterator behavior with captured payloads."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sortipy.adapters.spotify.client import SpotifyClient


def test_client_iterators_yield_items(spotipy_client: SpotifyClient) -> None:
    tracks = list(spotipy_client.iter_saved_tracks(max_items=1))
    albums = list(spotipy_client.iter_saved_albums(max_items=1))
    artists = list(spotipy_client.iter_followed_artists(max_items=1))

    assert len(tracks) == 1
    assert len(albums) == 1
    assert len(artists) == 1
