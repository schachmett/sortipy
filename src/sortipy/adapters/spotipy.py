"""Spotipy adapter"""

from __future__ import annotations

from datetime import date
from logging import getLogger
from typing import TYPE_CHECKING, Literal, Protocol, TypedDict, cast

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from sortipy.domain.types import Album, AlbumType, Artist, Provider

if TYPE_CHECKING:
    from collections.abc import Iterator


log = getLogger(__name__)


# common
class PaginatedResponse(TypedDict):
    href: str
    limit: int
    next: str
    offset: int
    previous: str
    total: int


# artist


class ArtistSimplePayload(TypedDict):
    external_urls: ExternalURLs
    href: str  # link to api endpoint for full artist object
    id: str
    name: str
    type: Literal["artist"]
    uri: str


class ArtistPayload(ArtistSimplePayload):
    followers: Followers
    genres: list[str]
    images: list[Image]
    popularity: int


# track


class TrackSimplePayload(TypedDict):
    artists: list[ArtistSimplePayload]
    available_markets: list[str]
    disc_number: int
    duration_ms: int
    explicit: bool
    external_urls: ExternalURLs
    href: str
    id: str
    is_playable: bool
    linked_from: LinkedFrom
    restrictions: Restrictions
    name: str
    track_number: int
    type: Literal["track"]
    uri: str
    is_local: bool


class TrackPayload(TrackSimplePayload):
    album: AlbumSimplePayload
    external_ids: ExternalIDs
    popularity: int


class TracksPayload(PaginatedResponse):
    items: list[TrackSimplePayload]


# album


class AlbumSimplePayload(TypedDict):
    album_type: Literal["album", "single", "compilation"]
    total_tracks: int
    available_markets: list[str]
    external_urls: ExternalURLs
    href: str
    id: str
    images: list[Image]
    name: str
    release_date: str
    release_date_precision: str
    restrictions: Restrictions  # not required
    type: Literal["album"]
    uri: str
    artists: list[ArtistSimplePayload]
    # album_group: str # only on simple?


class FullAlbumPayload(AlbumSimplePayload):
    tracks: TracksPayload
    copyrights: list[Copyright]
    external_ids: ExternalIDs
    label: str
    popularity: int


class SavedAlbumPayload(TypedDict):
    added_at: str
    album: FullAlbumPayload


class SavedAlbumsPayload(PaginatedResponse):
    items: list[SavedAlbumPayload]


class SpotifySavedAlbumClient(Protocol):
    def current_user_saved_albums(
        self,
        limit: int = ...,
        offset: int = ...,
        market: str | None = ...,
    ) -> SavedAlbumsPayload:
        ...

    def next(self, result: SavedAlbumsPayload) -> SavedAlbumsPayload:
        ...


# specifics


class ExternalURLs(TypedDict):
    spotify: str  # not required


class LinkedFrom(TypedDict):
    external_urls: ExternalURLs
    href: str
    id: str
    type: str
    uri: str


class Image(TypedDict):
    url: str
    height: int
    width: int


class Restrictions(TypedDict):
    reason: str


class Followers(TypedDict):
    total: int


class Copyright(TypedDict):
    text: str
    type: Literal["C"] | Literal["P"]


class ExternalIDs(TypedDict):
    isrc: str
    ean: str
    upc: str


DEFAULT_FETCH_LIMIT = 200
BATCH_SIZE = 50
SPOTIFY_SCOPE = "user-library-read"

# Date format lengths
YEAR_FORMAT_LENGTH = 4  # YYYY
YEAR_MONTH_FORMAT_LENGTH = 7  # YYYY-MM


class SpotifyAlbumFetcher:
    """Handles fetching and processing of Spotify saved albums."""

    def __init__(self, fetch_limit: int = DEFAULT_FETCH_LIMIT) -> None:
        self.spotify: SpotifySavedAlbumClient = self._setup_spotify_client()
        self.fetch_limit = fetch_limit

    def _setup_spotify_client(self) -> SpotifySavedAlbumClient:
        """Initialize and return an authenticated Spotify client."""
        client = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=SPOTIFY_SCOPE))
        return cast(SpotifySavedAlbumClient, client)

    def fetch_albums(self) -> Iterator[Album]:
        """Generator that yields album items from Spotify API."""
        response = self.spotify.current_user_saved_albums(limit=BATCH_SIZE)
        total_albums = response["total"]
        fetched_count = 0
        call_number = 1

        log.info(f"Total albums: {total_albums} - fetching only {self.fetch_limit}...")

        while True:
            items = response["items"]
            fetched_count += len(items)
            log.info(f"Fetched {fetched_count}/{self.fetch_limit} albums... ({call_number})")
            for saved in items:
                album_payload = saved["album"]
                release_date_str = album_payload["release_date"]
                if len(release_date_str) == YEAR_FORMAT_LENGTH:
                    release_date_str = f"{release_date_str}-01-01"
                elif len(release_date_str) == YEAR_MONTH_FORMAT_LENGTH:
                    release_date_str = f"{release_date_str}-01"

                try:
                    release_date_value = date.fromisoformat(release_date_str)
                except ValueError:
                    release_date_value = None

                primary_artist_payload = album_payload["artists"][0]
                primary_artist = Artist(
                    id=None,
                    name=primary_artist_payload["name"],
                    spotify_id=primary_artist_payload["id"],
                )
                primary_artist.add_source(Provider.SPOTIFY)

                album_entity = Album(
                    id=None,
                    name=album_payload["name"],
                    artist=primary_artist,
                    spotify_id=album_payload["id"],
                    album_type=AlbumType(album_payload["album_type"]),
                    release_date=release_date_value,
                )
                album_entity.add_source(Provider.SPOTIFY)
                primary_artist.albums.append(album_entity)

                yield album_entity

            if not response["next"] or fetched_count >= self.fetch_limit:
                break

            response = self.spotify.next(response)
            call_number += 1
