"""Spotipy adapter"""

from __future__ import annotations

from datetime import date
from logging import getLogger
from typing import TYPE_CHECKING, Literal, TypedDict, cast

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from sortipy.domain.types import AlbumType, ObjectType, SpotifyAlbum, SpotifyArtist

if TYPE_CHECKING:
    from collections.abc import Iterator

    from spotipy.client import Spotify


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


class ArtistSimple(TypedDict):
    external_urls: ExternalURLs
    href: str  # link to api endpoint for full artist object
    id: str
    name: str
    type: Literal["artist"]
    uri: str


class Artist(ArtistSimple):
    followers: Followers
    genres: list[str]
    images: list[Image]
    popularity: int


# track


class TrackSimple(TypedDict):
    artists: list[ArtistSimple]
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


class Track(TrackSimple):
    album: AlbumSimple
    external_ids: ExternalIDs
    popularity: int


class Tracks(PaginatedResponse):
    items: list[TrackSimple]


# album


class AlbumSimple(TypedDict):
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
    artists: list[ArtistSimple]
    # album_group: str # only on simple?


class FullAlbum(AlbumSimple):
    tracks: Tracks
    copyrights: list[Copyright]
    external_ids: ExternalIDs
    label: str
    popularity: int


class SavedAlbum(TypedDict):
    added_at: str
    album: FullAlbum


class SavedAlbums(PaginatedResponse):
    items: list[SavedAlbum]


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
        self.spotify = self._setup_spotify_client()
        self.fetch_limit = fetch_limit

    def _setup_spotify_client(self) -> Spotify:
        """Initialize and return an authenticated Spotify client."""
        return spotipy.Spotify(auth_manager=SpotifyOAuth(scope=SPOTIFY_SCOPE))

    def fetch_albums(self) -> Iterator[SpotifyAlbum]:
        """Generator that yields album items from Spotify API."""
        response = cast(SavedAlbums, self.spotify.current_user_saved_albums(limit=BATCH_SIZE))  # type: ignore[reportUnknownMemberType]
        total_albums = response["total"]
        fetched_count = 0
        call_number = 1

        log.info(f"Total albums: {total_albums} - fetching only {self.fetch_limit}...")

        while True:
            items = response["items"]
            fetched_count += len(items)
            log.info(f"Fetched {fetched_count}/{self.fetch_limit} albums... ({call_number})")
            for item in items:
                release_date = item["album"]["release_date"]
                if len(release_date) == YEAR_FORMAT_LENGTH:
                    release_date += "-01-01"
                elif len(release_date) == YEAR_MONTH_FORMAT_LENGTH:
                    release_date += "-01"
                year, month, day = item["album"]["release_date"].split("-")
                yield SpotifyAlbum(
                    spotify_id=item["album"]["id"],
                    name=item["album"]["name"],
                    artists=[
                        SpotifyArtist(
                            name=artist["name"], spotify_id=artist["id"], type=ObjectType.ARTIST
                        )
                        for artist in item["album"]["artists"]
                    ],
                    release_date=date(year=int(year), month=int(month), day=int(day)),
                    album_type=AlbumType(item["album"]["album_type"]),
                    total_tracks=item["album"]["total_tracks"],
                    type=ObjectType.ALBUM,
                )

            if not response["next"] or fetched_count >= self.fetch_limit:
                break

            response = cast(SavedAlbums, self.spotify.next(response))  # type: ignore[reportUnknownMemberType]
            call_number += 1
