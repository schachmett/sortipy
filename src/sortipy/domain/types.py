"""Common domain types used throughout the application."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date, datetime


@dataclass
class Image:
    height: int
    url: str
    width: int


class AlbumType(StrEnum):
    ALBUM = "album"
    SINGLE = "single"
    COMPILATION = "compilation"


class ObjectType(StrEnum):
    ALBUM = "album"
    ARTIST = "artist"
    TRACK = "track"


@dataclass
class SpotifyObject:
    spotify_id: str
    type: ObjectType

    @property
    def url(self) -> str:
        """Return the object's Spotify URL."""
        return f"https://open.spotify.com/{self.type}/{self.spotify_id}"

    @property
    def uri(self) -> str:
        """Return the object's Spotify URI."""
        return f"spotify:{self.type}:{self.spotify_id}"

    @property
    def api_url(self) -> str:
        """Return the object's Spotify API URL."""
        return f"https://api.spotify.com/v1/{self.type}s/{self.spotify_id}"


@dataclass
class ExternalIDs:
    isrc: str | None = None
    ean: str | None = None
    upc: str | None = None


@dataclass
class SpotifyArtist(SpotifyObject):
    name: str
    followers: int | None = None  # only in full artist object
    genres: list[str] | None = None  # only in full artist object
    popularity: int | None = None  # only in full artist object
    images: list[Image] | None = None  # only in full artist object
    type = ObjectType.ARTIST


@dataclass
class SpotifyAlbum(SpotifyObject):
    name: str
    artists: list[SpotifyArtist]
    total_tracks: int
    album_type: AlbumType
    release_date: date  # TODO: different precisions?
    tracks: list[SpotifyTrack] | None = None  # only in full album object
    external_ids: ExternalIDs = field(default_factory=ExternalIDs)  # only in full album object
    type = ObjectType.ALBUM


@dataclass
class SpotifyTrack(SpotifyObject):
    name: str
    disc_number: int
    track_number: int
    duration_ms: int
    explicit: bool
    artists: list[SpotifyArtist]  # only in full track object
    album: SpotifyAlbum | None = None  # only in full track object
    external_ids: ExternalIDs = field(default_factory=ExternalIDs)  # only in full track object
    type = ObjectType.TRACK


@dataclass
class LastFMObject:
    id: str | None
    mbid: str | None  # MusicBrainz ID, often empty in Last.fm responses
    type: ObjectType
    playcount: int | None  # only in full objects


@dataclass
class LastFMArtist(LastFMObject):
    name: str
    type = ObjectType.ARTIST
    albums: list[LastFMAlbum] = field(default_factory=list)
    tracks: list[LastFMTrack] = field(default_factory=list)


@dataclass
class LastFMAlbum(LastFMObject):
    name: str
    artist: LastFMArtist
    type = ObjectType.ALBUM
    tracks: list[LastFMTrack] = field(default_factory=list)


@dataclass
class LastFMTrack(LastFMObject):
    name: str
    artist: LastFMArtist
    album: LastFMAlbum
    type = ObjectType.TRACK
    scrobbles: list[LastFMScrobble] = field(default_factory=list)


@dataclass
class LastFMScrobble:
    timestamp: datetime
    track: LastFMTrack


@dataclass
class MergedAlbum:
    """Represents a Spotify album with essential metadata."""

    release_date: str
    title: str
    artists: str

    def __str__(self) -> str:
        """Return a formatted string representation of the album."""
        return f"{self.release_date} - {self.title} - {self.artists}"
