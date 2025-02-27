"""Spotipy adapter"""

from __future__ import annotations

from typing import Literal, TypedDict


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
    href: str
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
    album_type: Literal["album"] | Literal["single"] | Literal["compilation"]
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


class Album(AlbumSimple):
    tracks: Tracks
    copyrights: list[Copyright]
    external_ids: ExternalIDs
    label: str
    popularity: int


class SavedAlbum(TypedDict):
    added_at: str
    album: Album


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
