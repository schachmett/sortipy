"""Canonical domain model used across Sortipy."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID  # noqa: TC003 # UUID is needed at runtime (SQLAlchemy)

# Basic aliases (PEP 695) so we can upgrade to value objects later.
type CountryCode = str
type CatalogNumber = str
type Barcode = str
type Mbid = str
type Isrc = str
type DurationMs = int


class Provider(StrEnum):
    """External systems that can contribute data or provenance."""

    LASTFM = "lastfm"
    SPOTIFY = "spotify"
    MUSICBRAINZ = "musicbrainz"


class ExternalNamespace(StrEnum):
    """Convenience constants for commonly used external-ID namespaces."""

    MUSICBRAINZ_ARTIST = "musicbrainz:artist"
    MUSICBRAINZ_RELEASE_GROUP = "musicbrainz:release-group"
    MUSICBRAINZ_RELEASE = "musicbrainz:release"
    MUSICBRAINZ_RECORDING = "musicbrainz:recording"
    MUSICBRAINZ_LABEL = "musicbrainz:label"
    SPOTIFY_ARTIST = "spotify:artist"
    RECORDING_ISRC = "recording:isrc"
    LABEL_CATALOG_NUMBER = "label:catalog_number"
    LABEL_BARCODE = "label:barcode"
    USER_SPOTIFY = "spotify:user"
    USER_LASTFM = "lastfm:user"


type Namespace = str | ExternalNamespace  # identifies external system for an ExternalID


class ArtistRole(StrEnum):
    """Role descriptor shared by release-set and recording artist associations."""

    PRIMARY = "primary"
    FEATURED = "featured"
    PRODUCER = "producer"
    COMPOSER = "composer"
    CONDUCTOR = "conductor"


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


class CanonicalEntityType(StrEnum):
    """Canonical entity types used throughout the domain."""

    ARTIST = "artist"
    RELEASE_SET = "release_set"
    RELEASE = "release"
    RECORDING = "recording"
    TRACK = "track"
    LABEL = "label"


class MergeReason(StrEnum):
    """Reasons for pointing one entity at another."""

    MANUAL = "manual"


@dataclass(frozen=True)
class PartialDate:
    """Represents a year/month/day triplet that might be partially specified."""

    year: int | None = None
    month: int | None = None
    day: int | None = None

    @property
    def as_date(self) -> date | None:
        if self.year is None:
            return None
        month = self.month or 1
        day = self.day or 1
        return date(self.year, month, day)

    def __composite_values__(self) -> tuple[int | None, int | None, int | None]:
        """Return values in a shape suitable for SQLAlchemy composite columns."""
        return (self.year, self.month, self.day)


@dataclass
class ExternalID:
    """Record linking a canonical entity to an identifier from an external catalogue.

    The ``namespace`` identifies the provider and type of identifier (for example
    ``"musicbrainz:recording"`` or ``"spotify:album"``) so multiple IDs can coexist per entity
    without adding provider-specific columns. See :class:`ExternalNamespace` for convenience
    constants covering common namespaces; arbitrary strings remain valid for new providers.
    """

    namespace: Namespace
    value: str
    entity_type: CanonicalEntityType
    entity_id: UUID | None = None
    provider: Provider | None = None
    created_at: datetime | None = None


@dataclass(kw_only=True)
class IngestedEntity:
    """Shared fields for objects produced by an ingestion run.

    ``raw_payload_id`` and ``ingested_at`` provide the minimal hooks needed to tie back to the
    underlying raw record (see ADR 0007 for the full provenance story).
    """

    raw_payload_id: UUID | None = None
    ingested_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    # NOTE: swap for a typed raw-payload reference after implementing ADR 0007.


@dataclass(kw_only=True)
class CanonicalEntity(IngestedEntity):
    """Base mixin for canonical entities that may be merged and enriched.

    Canonical rows use ``canonical_id`` to implement the pointer-based merge pattern from
    ADR 0008—consumers should consult ``identity`` for a stable identifier. The provenance fields
    capture which upstream providers contributed data so refresh pipelines can make informed
    decisions about how to reconcile updates.
    """

    id: UUID | None = None
    canonical_id: UUID | None = None
    updated_at: datetime | None = None
    sources: set[Provider] = field(default_factory=set[Provider])
    external_ids: list[ExternalID] = field(default_factory=list[ExternalID])

    @property
    def identity(self) -> UUID | None:
        """Return the canonical identifier when present, otherwise the local id."""
        return self.canonical_id or self.id

    @property
    def entity_type(self) -> CanonicalEntityType:
        raise NotImplementedError

    def add_external_id(self, external_id: ExternalID, *, replace: bool = False) -> None:
        if replace:
            self.external_ids = [
                existing
                for existing in self.external_ids
                if existing.namespace != external_id.namespace
            ]
        self.external_ids.append(external_id)

    @property
    def external_ids_by_namespace(self) -> dict[Namespace, ExternalID]:
        """Return the latest external ID per namespace for convenient lookups."""
        mapping: dict[Namespace, ExternalID] = {}
        for external_id in self.external_ids:
            mapping[external_id.namespace] = external_id
        return mapping


@dataclass
class Artist(CanonicalEntity):
    """Canonical representation of an artist.

    Common external identifiers are carried via :class:`ExternalID`, e.g. ``musicbrainz:artist``.
    """

    name: str
    sort_name: str | None = None
    country: CountryCode | None = None
    formed_year: int | None = None
    disbanded_year: int | None = None
    # list[T] remains callable on Python >= 3.12, which keeps pyright happy about the element type.
    release_sets: list[ReleaseSet] = field(default_factory=list["ReleaseSet"])
    recordings: list[Recording] = field(default_factory=list["Recording"])

    @property
    def entity_type(self) -> CanonicalEntityType:
        return CanonicalEntityType.ARTIST


@dataclass
class ReleaseSet(CanonicalEntity):
    """Conceptual collection of releases (e.g., an album and its editions).

    Common external identifiers: ``musicbrainz:release-group``.
    """

    title: str
    primary_type: ReleaseSetType | None = None
    first_release: PartialDate | None = None
    releases: list[Release] = field(default_factory=list["Release"])
    artists: list[ReleaseSetArtist] = field(default_factory=list["ReleaseSetArtist"])

    @property
    def entity_type(self) -> CanonicalEntityType:
        return CanonicalEntityType.RELEASE_SET


@dataclass
class Label(CanonicalEntity):
    """Music label or publisher.

    Common external identifiers: ``musicbrainz:label``.
    """

    name: str
    country: CountryCode | None = None

    @property
    def entity_type(self) -> CanonicalEntityType:
        return CanonicalEntityType.LABEL


@dataclass
class Release(CanonicalEntity):
    """Concrete manifestation of a release (e.g., region-specific edition).

    Common external identifiers (catalog numbers, barcodes, MusicBrainz release IDs) live in
    :class:`ExternalID` rows.
    """

    title: str
    release_set: ReleaseSet
    release_date: PartialDate | None = None
    country: CountryCode | None = None
    labels: list[Label] = field(default_factory=list[Label])
    format: str | None = None
    medium_count: int | None = None
    tracks: list[Track] = field(default_factory=list["Track"])

    @property
    def entity_type(self) -> CanonicalEntityType:
        return CanonicalEntityType.RELEASE


@dataclass
class Recording(CanonicalEntity):
    """Specific performance or mix of a composition.

    Common external identifiers (ISRC, MusicBrainz recording IDs) live in :class:`ExternalID` rows.
    """

    title: str
    duration_ms: DurationMs | None = None
    version: str | None = None
    tracks: list[Track] = field(default_factory=list["Track"])
    play_events: list[PlayEvent] = field(default_factory=list["PlayEvent"])
    artists: list[RecordingArtist] = field(default_factory=list["RecordingArtist"])

    @property
    def entity_type(self) -> CanonicalEntityType:
        return CanonicalEntityType.RECORDING


@dataclass
class Track(CanonicalEntity):
    """Placement of a recording on a specific release."""

    release: Release
    recording: Recording
    disc_number: int | None = None
    track_number: int | None = None
    title_override: str | None = None
    duration_ms: DurationMs | None = None
    play_events: list[PlayEvent] = field(default_factory=list["PlayEvent"])

    @property
    def entity_type(self) -> CanonicalEntityType:
        return CanonicalEntityType.TRACK


@dataclass(kw_only=True)
class User(IngestedEntity):
    """Local representation of a listener."""

    id: UUID | None = None
    display_name: str
    email: str | None = None
    spotify_user_id: str | None = None  # Denormalized external account identifier.
    lastfm_user: str | None = None  # Denormalized external account identifier.
    created_at: datetime | None = None
    updated_at: datetime | None = None
    library_items: list[LibraryItem] = field(default_factory=list["LibraryItem"])


@dataclass(kw_only=True)
class PlayEvent(IngestedEntity):
    """A listener consuming a recording at a point in time."""

    played_at: datetime
    source: Provider
    recording: Recording
    user: User | None = None
    track: Track | None = None
    duration_ms: DurationMs | None = None


@dataclass(kw_only=True)
class LibraryItem(IngestedEntity):
    """User saved items (artists, releases, recordings, etc.).

    The ``entity`` attribute holds a direct reference to the canonical object the user saved, which
    allows domain code to navigate without issuing additional lookups. When persistence needs an ID,
    it can read ``entity.identity``. Persistence stores the canonical type and identifier explicitly
    (``entity_type`` and ``entity_id``) because there is no single foreign key that can point at
    every canonical table. The ``entity`` attribute is therefore an optional in-memory
    convenience—callers may hydrate it when the referenced row is already available, but storage and
    reloads only rely on the polymorphic ID pair.
    """

    user: User
    entity_type: CanonicalEntityType
    entity_id: UUID
    entity: CanonicalEntity | None = None
    source: Provider | None = None
    saved_at: datetime | None = None


@dataclass
class ReleaseSetArtist:
    """Relationship between a release set and an artist with role metadata."""

    release_set: ReleaseSet
    artist: Artist
    role: ArtistRole | None = None
    credit_order: int | None = None


@dataclass
class RecordingArtist:
    """Relationship between a recording and an artist with detailed roles."""

    recording: Recording
    artist: Artist
    role: ArtistRole | None = None
    instrument: str | None = None
    credit_order: int | None = None


@dataclass
class EntityMerge:
    """Audit record for pointing a duplicate entity to its canonical counterpart."""

    entity_type: CanonicalEntityType
    source_id: UUID
    target_id: UUID
    reason: MergeReason = MergeReason.MANUAL
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    created_by: str | None = None


__all__ = [
    "Artist",
    "ArtistRole",
    "Barcode",
    "CanonicalEntity",
    "CanonicalEntityType",
    "CatalogNumber",
    "CountryCode",
    "DurationMs",
    "EntityMerge",
    "ExternalID",
    "ExternalNamespace",
    "IngestedEntity",
    "Isrc",
    "Label",
    "LibraryItem",
    "Mbid",
    "MergeReason",
    "Namespace",
    "PartialDate",
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
