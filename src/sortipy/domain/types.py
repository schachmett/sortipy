"""Canonical domain model used across Sortipy."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date, datetime
    from uuid import UUID


class Provider(StrEnum):
    """External systems that can contribute data."""

    LASTFM = "lastfm"
    SPOTIFY = "spotify"
    MUSICBRAINZ = "musicbrainz"
    RATEYOURMUSIC = "rateyourmusic"


class AlbumType(StrEnum):
    ALBUM = "album"
    SINGLE = "single"
    COMPILATION = "compilation"
    EP = "ep"
    LIVE = "live"
    OTHER = "other"


def _provider_set() -> set[Provider]:
    return set()


def _album_list() -> list[Album]:
    return []


def _track_list() -> list[Track]:
    return []


def _scrobble_list() -> list[Scrobble]:
    return []


@dataclass
class Artist:
    """Canonical representation of an artist."""

    name: str
    id: UUID | None = None
    mbid: str | None = None  # MusicBrainz identifier (when known)
    spotify_id: str | None = None
    playcount: int | None = None
    sources: set[Provider] = field(default_factory=_provider_set)
    albums: list[Album] = field(default_factory=_album_list, repr=False)
    tracks: list[Track] = field(default_factory=_track_list, repr=False)

    def add_source(self, provider: Provider) -> None:
        self.sources.add(provider)


@dataclass
class Album:
    """Canonical representation of an album/release."""

    name: str
    artist: Artist
    id: UUID | None = None
    mbid: str | None = None
    spotify_id: str | None = None
    album_type: AlbumType | None = None
    release_date: date | None = None
    playcount: int | None = None
    sources: set[Provider] = field(default_factory=_provider_set)
    tracks: list[Track] = field(default_factory=_track_list, repr=False)

    def add_track(self, track: Track) -> None:
        if track not in self.tracks:
            self.tracks.append(track)

    def add_source(self, provider: Provider) -> None:
        self.sources.add(provider)


@dataclass
class Track:
    """Canonical representation of a track."""

    name: str
    artist: Artist
    album: Album
    id: UUID | None = None
    mbid: str | None = None
    spotify_id: str | None = None
    duration_ms: int | None = None
    disc_number: int | None = None
    track_number: int | None = None
    playcount: int | None = None
    sources: set[Provider] = field(default_factory=_provider_set)
    scrobbles: list[Scrobble] = field(default_factory=_scrobble_list, repr=False)

    def add_scrobble(self, scrobble: Scrobble) -> None:
        if scrobble not in self.scrobbles:
            self.scrobbles.append(scrobble)

    def add_source(self, provider: Provider) -> None:
        self.sources.add(provider)


@dataclass
class Scrobble:
    """A listening event for a track."""

    timestamp: datetime
    track: Track
    provider: Provider = Provider.LASTFM


@dataclass
class LibrarySnapshot:
    """Aggregated view of the user's library."""

    artists: list[Artist]
    albums: list[Album]
    tracks: list[Track]
    scrobbles: list[Scrobble]
