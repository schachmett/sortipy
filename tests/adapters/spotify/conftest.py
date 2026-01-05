"""Shared fixtures for Spotify adapter tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sortipy.adapters.spotify.client import SpotifyClient, SpotifyConfig

SpotifyPayload = dict[str, object]
FIXTURES = Path("tests/data/spotify")


def _load_fixture(name: str) -> SpotifyPayload:
    return json.loads((FIXTURES / name).read_text())


class FakeSpotipyClient:
    def __init__(
        self, tracks: SpotifyPayload, albums: SpotifyPayload, artists: SpotifyPayload
    ) -> None:
        self._tracks = tracks
        self._albums = albums
        self._artists = artists

    def current_user_saved_tracks(self, *, limit: int, offset: int) -> SpotifyPayload:
        del limit, offset
        return self._tracks

    def current_user_saved_albums(self, *, limit: int, offset: int) -> SpotifyPayload:
        del limit, offset
        return self._albums

    def current_user_followed_artists(
        self, *, limit: int, after: str | None = None
    ) -> SpotifyPayload:
        del limit, after
        return self._artists


@pytest.fixture
def spotify_payloads() -> tuple[SpotifyPayload, SpotifyPayload, SpotifyPayload]:
    return (
        _load_fixture("saved_tracks_raw.json"),
        _load_fixture("saved_albums_raw.json"),
        _load_fixture("followed_artists_raw.json"),
    )


@pytest.fixture
def fake_spotify_client(
    spotify_payloads: tuple[SpotifyPayload, SpotifyPayload, SpotifyPayload],
) -> FakeSpotipyClient:
    tracks_payload, albums_payload, artists_payload = spotify_payloads
    return FakeSpotipyClient(tracks_payload, albums_payload, artists_payload)


@pytest.fixture
def spotify_config() -> SpotifyConfig:
    return SpotifyConfig(
        client_id="x",
        client_secret="y",  # noqa: S106
        redirect_uri="http://localhost",
    )


@pytest.fixture
def spotipy_client(
    spotify_config: SpotifyConfig, fake_spotify_client: FakeSpotipyClient
) -> SpotifyClient:
    return SpotifyClient(config=spotify_config, client=fake_spotify_client)
