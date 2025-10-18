"""Canonical domain model used across Sortipy."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID


class Provider(StrEnum):
    """External systems that can contribute data or provenance."""

    LASTFM = "lastfm"
    SPOTIFY = "spotify"
    MUSICBRAINZ = "musicbrainz"
    DISCOGS = "discogs"
    RATEYOURMUSIC = "rateyourmusic"
    BANDCAMP = "bandcamp"


class ReleaseSetType(StrEnum):
    """Primary classification for a release set (conceptual album)."""

    ALBUM = "album"
    SINGLE = "single"
    EP = "ep"
    LIVE = "live"
    COMPILATION = "compilation"
    SOUNDTRACK = "soundtrack"
    MIXTAPE = "mixtape"
    OTHER = "other"


class LibraryEntityType(StrEnum):
    """Entity types that can be referenced from user libraries or external IDs."""

    ARTIST = "artist"
    RELEASE_SET = "release_set"
    RELEASE = "release"
    RECORDING = "recording"
    TRACK = "track"
    USER = "user"


def _provider_set() -> set[Provider]:
    return set()


def _external_id_list() -> list[ExternalID]:
    return []


def _release_list() -> list[Release]:
    return []


def _recording_list() -> list[Recording]:
    return []


def _track_list() -> list[Track]:
    return []


def _play_event_list() -> list[PlayEvent]:
    return []


def _library_item_list() -> list[LibraryItem]:
    return []


@dataclass
class Artist:
    """Canonical representation of an artist."""

    name: str
    id: UUID | None = None
    canonical_id: UUID | None = None
    sort_name: str | None = None
    country: str | None = None
    formed_year: int | None = None
    disbanded_year: int | None = None
    mbid: str | None = None
    notes: str | None = None
    sources: set[Provider] = field(default_factory=_provider_set)
    external_ids: list[ExternalID] = field(default_factory=_external_id_list, repr=False)
    release_sets: list[ReleaseSet] = field(default_factory=list, repr=False)
    recordings: list[Recording] = field(default_factory=_recording_list, repr=False)

    def add_source(self, provider: Provider) -> None:
        self.sources.add(provider)


@dataclass
class ReleaseSet:
    """Conceptual collection of releases (e.g., an album and its editions)."""

    title: str
    primary_artist: Artist | None
    id: UUID | None = None
    canonical_id: UUID | None = None
    primary_type: ReleaseSetType | None = None
    secondary_types: list[ReleaseSetType] = field(default_factory=list)
    first_release_year: int | None = None
    first_release_month: int | None = None
    first_release_day: int | None = None
    mbid: str | None = None
    summary: str | None = None
    sources: set[Provider] = field(default_factory=_provider_set)
    external_ids: list[ExternalID] = field(default_factory=_external_id_list, repr=False)
    releases: list[Release] = field(default_factory=_release_list, repr=False)
    artists: list[ReleaseSetArtist] = field(default_factory=list, repr=False)

    def add_source(self, provider: Provider) -> None:
        self.sources.add(provider)


@dataclass
class Release:
    """Concrete manifestation of a release (e.g., region-specific edition)."""

    title: str
    release_set: ReleaseSet
    id: UUID | None = None
    canonical_id: UUID | None = None
    date_year: int | None = None
    date_month: int | None = None
    date_day: int | None = None
    country: str | None = None
    label: str | None = None
    catalog_number: str | None = None
    barcode: str | None = None
    format: str | None = None
    medium_count: int | None = None
    packaging: str | None = None
    mbid: str | None = None
    sources: set[Provider] = field(default_factory=_provider_set)
    external_ids: list[ExternalID] = field(default_factory=_external_id_list, repr=False)
    tracks: list[Track] = field(default_factory=_track_list, repr=False)

    def add_source(self, provider: Provider) -> None:
        self.sources.add(provider)


@dataclass
class Recording:
    """Specific performance or mix of a composition."""

    title: str
    primary_artist: Artist | None
    id: UUID | None = None
    canonical_id: UUID | None = None
    duration_ms: int | None = None
    isrc: str | None = None
    mbid: str | None = None
    version: str | None = None
    mix_hint: str | None = None
    work_id: UUID | None = None
    sources: set[Provider] = field(default_factory=_provider_set)
    external_ids: list[ExternalID] = field(default_factory=_external_id_list, repr=False)
    tracks: list[Track] = field(default_factory=_track_list, repr=False)
    play_events: list[PlayEvent] = field(default_factory=_play_event_list, repr=False)
    artists: list[RecordingArtist] = field(default_factory=list, repr=False)

    def add_source(self, provider: Provider) -> None:
        self.sources.add(provider)


@dataclass
class Track:
    """Placement of a recording on a specific release."""

    release: Release
    recording: Recording
    id: UUID | None = None
    canonical_id: UUID | None = None
    disc_number: int | None = None
    track_number: int | None = None
    position: int | None = None
    title_override: str | None = None
    duration_ms: int | None = None
    sources: set[Provider] = field(default_factory=_provider_set)
    external_ids: list[ExternalID] = field(default_factory=_external_id_list, repr=False)
    play_events: list[PlayEvent] = field(default_factory=_play_event_list, repr=False)

    def add_source(self, provider: Provider) -> None:
        self.sources.add(provider)


@dataclass
class User:
    """Local representation of a listener."""

    display_name: str
    id: UUID | None = None
    canonical_id: UUID | None = None
    spotify_user_id: str | None = None
    lastfm_user: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    library_items: list[LibraryItem] = field(default_factory=_library_item_list, repr=False)
    external_ids: list[ExternalID] = field(default_factory=_external_id_list, repr=False)


@dataclass
class PlayEvent:
    """A listener consuming a recording at a point in time."""

    played_at: datetime
    recording: Recording
    provider: Provider
    id: UUID | None = None
    user: User | None = None
    track: Track | None = None
    release: Release | None = None
    release_set: ReleaseSet | None = None
    source_play_id: str | None = None
    source_context: str | None = None
    device_name: str | None = None
    duration_ms: int | None = None
    confidence: float | None = None
    raw_payload_id: UUID | None = None
    ingested_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


@dataclass
class ExternalID:
    """Mapping between a canonical entity and an external identifier."""

    namespace: str
    value: str
    entity_type: LibraryEntityType
    provider: Provider | None = None
    id: UUID | None = None
    entity_id: UUID | None = None
    created_at: datetime | None = None
    note: str | None = None


@dataclass
class LibraryItem:
    """User saved items (artists, releases, recordings, etc.)."""

    user: User
    entity_type: LibraryEntityType
    entity_id: UUID
    id: UUID | None = None
    saved_from: Provider | None = None
    saved_at: datetime | None = None
    source_context: str | None = None


@dataclass
class ReleaseSetArtist:
    """Relationship between a release set and an artist with role metadata."""

    release_set: ReleaseSet
    artist: Artist
    role: str | None = None
    position: int | None = None


@dataclass
class RecordingArtist:
    """Relationship between a recording and an artist with detailed roles."""

    recording: Recording
    artist: Artist
    role: str | None = None
    instrument: str | None = None
    credit_order: int | None = None


@dataclass
class EntityMerge:
    """Audit record for pointing a duplicate entity to its canonical counterpart."""

    entity_type: LibraryEntityType
    source_id: UUID
    target_id: UUID
    reason: str | None = None
    confidence: float | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    created_by: str | None = None


__all__ = [
    "Artist",
    "EntityMerge",
    "ExternalID",
    "LibraryEntityType",
    "LibraryItem",
    "PlayEvent",
    "Provider",
    "Recording",
    "RecordingArtist",
    "Release",
    "ReleaseSet",
    "ReleaseSetArtist",
    "ReleaseSetType",
    "Track",
    "User",
]
