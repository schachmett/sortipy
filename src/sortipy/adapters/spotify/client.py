"""Spotipy-based client wrapper for Spotify Web API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from .schema import (
    FollowedArtistsResponse,
    SavedAlbumsPage,
    SavedTracksPage,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sortipy.config.spotify import SpotifyConfig

    from .schema import (
        SavedAlbumItem,
        SavedTrackItem,
        SpotifyArtist,
    )


class SpotifyApiClient(Protocol):
    def current_user_saved_tracks(self, *, limit: int, offset: int) -> dict[str, object]: ...

    def current_user_saved_albums(self, *, limit: int, offset: int) -> dict[str, object]: ...

    def current_user_followed_artists(
        self, *, limit: int, after: str | None = None
    ) -> dict[str, object]: ...


class SpotifyClient:
    """Small wrapper around spotipy.Spotify for paging helpers."""

    def __init__(self, *, config: SpotifyConfig, client: SpotifyApiClient | None = None) -> None:
        if client is None:
            cache_handler = (
                spotipy.CacheFileHandler(config.cache_path)
                if config.cache_path is not None
                else None
            )
            auth_manager = SpotifyOAuth(
                client_id=config.client_id,
                client_secret=config.client_secret,
                redirect_uri=config.redirect_uri,
                scope=" ".join(config.scope),
                cache_handler=cache_handler,
            )
            client = spotipy.Spotify(auth_manager=auth_manager)
        self._client: SpotifyApiClient = client

    def iter_saved_tracks(
        self,
        *,
        batch_size: int = 50,
        max_items: int | None = None,
    ) -> Iterable[SavedTrackItem]:
        offset = 0
        yielded = 0
        while True:
            raw_payload = self._client.current_user_saved_tracks(limit=batch_size, offset=offset)
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
            raw_payload = self._client.current_user_saved_albums(limit=batch_size, offset=offset)
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
            raw_payload = self._client.current_user_followed_artists(limit=batch_size, after=after)
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
