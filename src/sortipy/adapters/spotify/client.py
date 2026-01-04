"""Spotipy-based client wrapper for Spotify Web API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from sortipy.common.config import require_env_vars

from .schema import (
    FollowedArtistsResponse,
    SavedAlbumItem,
    SavedAlbumsPage,
    SavedTrackItem,
    SavedTracksPage,
    SpotifyArtist,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


DEFAULT_SPOTIFY_SCOPES = (
    "user-library-read",
    "user-follow-read",
)


@dataclass(frozen=True)
class SpotifyScopes:
    library: tuple[str, ...] = DEFAULT_SPOTIFY_SCOPES
    recently_played: tuple[str, ...] = ("user-read-recently-played",)
    currently_playing: tuple[str, ...] = (
        "user-read-currently-playing",
        "user-read-playback-state",
    )

    @staticmethod
    def merge(*scopes: tuple[str, ...]) -> tuple[str, ...]:
        merged: list[str] = []
        for scope_list in scopes:
            for scope in scope_list:
                if scope not in merged:
                    merged.append(scope)
        return tuple(merged)


@dataclass(frozen=True)
class SpotifyConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    scope: tuple[str, ...] = field(default_factory=lambda: SpotifyScopes.library)

    @classmethod
    def from_environment(cls, *, scope: tuple[str, ...] | None = None) -> SpotifyConfig:
        values = require_env_vars(
            ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REDIRECT_URI")
        )
        return cls(
            client_id=values["SPOTIFY_CLIENT_ID"],
            client_secret=values["SPOTIFY_CLIENT_SECRET"],
            redirect_uri=values["SPOTIFY_REDIRECT_URI"],
            scope=scope or SpotifyScopes.library,
        )


class SpotifyClient:
    """Small wrapper around spotipy.Spotify for paging helpers."""

    def __init__(self, *, config: SpotifyConfig, client: spotipy.Spotify | None = None) -> None:
        if client is None:
            auth_manager = SpotifyOAuth(
                client_id=config.client_id,
                client_secret=config.client_secret,
                redirect_uri=config.redirect_uri,
                scope=" ".join(config.scope),
            )
            client = spotipy.Spotify(auth_manager=auth_manager)
        self._client = client

    def iter_saved_tracks(
        self,
        *,
        batch_size: int = 50,
        max_items: int | None = None,
    ) -> Iterable[SavedTrackItem]:
        offset = 0
        yielded = 0
        while True:
            raw_payload = self._client.current_user_saved_tracks(limit=batch_size, offset=offset)  # pyright: ignore[reportUnknownMemberType]
            payload = SavedTracksPage.model_validate(raw_payload)
            items = payload.items
            if not items:
                return
            for item in items:
                yield item
                yielded += 1
                if max_items is not None and yielded >= max_items:
                    return
            if payload.next is None:
                return
            offset += len(items)

    def iter_saved_albums(
        self,
        *,
        batch_size: int = 50,
        max_items: int | None = None,
    ) -> Iterable[SavedAlbumItem]:
        offset = 0
        yielded = 0
        while True:
            raw_payload = self._client.current_user_saved_albums(limit=batch_size, offset=offset)  # pyright: ignore[reportUnknownMemberType]
            payload = SavedAlbumsPage.model_validate(raw_payload)
            items = payload.items
            if not items:
                return
            for item in items:
                yield item
                yielded += 1
                if max_items is not None and yielded >= max_items:
                    return
            if payload.next is None:
                return
            offset += len(items)

    def iter_followed_artists(
        self,
        *,
        batch_size: int = 50,
        max_items: int | None = None,
    ) -> Iterable[SpotifyArtist]:
        after: str | None = None
        yielded = 0
        while True:
            raw_payload = self._client.current_user_followed_artists(limit=batch_size, after=after)  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
            payload = FollowedArtistsResponse.model_validate(raw_payload)
            artists = payload.artists
            items = artists.items
            if not items:
                return
            for item in items:
                yield item
                yielded += 1
                if max_items is not None and yielded >= max_items:
                    return
            after = artists.cursors.after if artists.cursors is not None else None
            if not after:
                return
