"""Spotify library importer (saved tracks/albums/followed artists)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sortipy.domain.ports.fetching import LibraryItemFetchResult

from .client import SpotifyClient
from .translator import translate_followed_artist, translate_saved_album, translate_saved_track

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sortipy.config.spotify import SpotifyConfig
    from sortipy.domain.model import LibraryItem, User


def fetch_library_items(
    *,
    config: SpotifyConfig,
    client: SpotifyClient | None = None,
    user: User,
    batch_size: int = 50,
    max_tracks: int | None = None,
    max_albums: int | None = None,
    max_artists: int | None = None,
) -> LibraryItemFetchResult:
    """Fetch Spotify library items and translate them into domain entities."""

    active_client = client or SpotifyClient(config=config)
    return LibraryItemFetchResult(
        library_items=_iter_library_items(
            active_client,
            user=user,
            batch_size=batch_size,
            max_tracks=max_tracks,
            max_albums=max_albums,
            max_artists=max_artists,
        )
    )


def _iter_library_items(
    client: SpotifyClient,
    *,
    user: User,
    batch_size: int,
    max_tracks: int | None,
    max_albums: int | None,
    max_artists: int | None,
) -> Iterable[LibraryItem]:
    yield from _iter_saved_tracks(
        client,
        user=user,
        batch_size=batch_size,
        max_items=max_tracks,
    )
    yield from _iter_saved_albums(
        client,
        user=user,
        batch_size=batch_size,
        max_items=max_albums,
    )
    yield from _iter_followed_artists(
        client,
        user=user,
        batch_size=batch_size,
        max_items=max_artists,
    )


def _iter_saved_tracks(
    client: SpotifyClient,
    *,
    user: User,
    batch_size: int,
    max_items: int | None,
) -> Iterable[LibraryItem]:
    for item in client.iter_saved_tracks(batch_size=batch_size, max_items=max_items):
        yield translate_saved_track(item.track, user=user)


def _iter_saved_albums(
    client: SpotifyClient,
    *,
    user: User,
    batch_size: int,
    max_items: int | None,
) -> Iterable[LibraryItem]:
    for item in client.iter_saved_albums(batch_size=batch_size, max_items=max_items):
        yield translate_saved_album(item.album, user=user)


def _iter_followed_artists(
    client: SpotifyClient,
    *,
    user: User,
    batch_size: int,
    max_items: int | None,
) -> Iterable[LibraryItem]:
    for item in client.iter_followed_artists(batch_size=batch_size, max_items=max_items):
        yield translate_followed_artist(item, user=user)
