"""Domain update DTOs (source-agnostic)."""

# switch off type warnings because of default_factory=list or set
# pyright: reportUnknownVariableType=false

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sortipy.domain.model import (
        Area,
        ArtistKind,
        ArtistRole,
        CatalogNumber,
        CountryCode,
        LifeSpan,
        Mbid,
        Namespace,
        PartialDate,
        Provider,
        ReleasePackaging,
        ReleaseSetSecondaryType,
        ReleaseSetType,
        ReleaseStatus,
    )


@dataclass(slots=True)
class ExternalIdUpdate:
    """External identifier update for any entity."""

    namespace: Namespace
    value: str


@dataclass(slots=True)
class EnrichmentMetadata:
    """Metadata attached to enrichment updates."""

    source: Provider
    confidence: float = 0.0


@dataclass(slots=True)
class LabelUpdate:
    """Label info update for releases."""

    name: str | None = None
    catalog_number: CatalogNumber | None = None
    external_ids: list[ExternalIdUpdate] = field(default_factory=list)


@dataclass(slots=True)
class ArtistUpdate:
    """Enrichment update for an artist."""

    metadata: EnrichmentMetadata
    name: str
    external_ids: list[ExternalIdUpdate] = field(default_factory=list)
    sort_name: str | None = None
    disambiguation: str | None = None
    country: CountryCode | None = None
    kind: ArtistKind | None = None
    aliases: list[str] = field(default_factory=list)
    life_span: LifeSpan | None = None
    areas: list[Area] = field(default_factory=list)


@dataclass(slots=True)
class ContributionUpdate:
    """Artist contribution update for a recording or release set."""

    artist: ArtistUpdate
    role: ArtistRole
    credit_order: int | None = None
    credited_as: str | None = None
    join_phrase: str | None = None


@dataclass(slots=True)
class ReleaseSetUpdate:
    """Enrichment update for a release group (release set)."""

    metadata: EnrichmentMetadata
    title: str
    external_ids: list[ExternalIdUpdate] = field(default_factory=list)
    disambiguation: str | None = None
    primary_type: ReleaseSetType | None = None
    secondary_types: list[ReleaseSetSecondaryType] = field(default_factory=list)
    first_release_date: PartialDate | None = None
    aliases: list[str] = field(default_factory=list)
    contributions: list[ContributionUpdate] = field(default_factory=list)


@dataclass(slots=True)
class RecordingUpdate:
    """Enrichment update for a recording."""

    metadata: EnrichmentMetadata
    title: str
    external_ids: list[ExternalIdUpdate] = field(default_factory=list)
    disambiguation: str | None = None
    duration_ms: int | None = None
    aliases: list[str] = field(default_factory=list)
    contributions: list[ContributionUpdate] = field(default_factory=list)


@dataclass(slots=True)
class ReleaseTrackUpdate:
    """Link a recording update to a release track position."""

    recording: RecordingUpdate
    disc_number: int | None = None
    track_number: int | None = None
    title_override: str | None = None
    duration_ms: int | None = None


@dataclass(slots=True)
class ReleaseUpdate:
    """Enrichment update for a release."""

    metadata: EnrichmentMetadata
    title: str
    external_ids: list[ExternalIdUpdate] = field(default_factory=list)
    disambiguation: str | None = None
    release_date: PartialDate | None = None
    country: CountryCode | None = None
    status: ReleaseStatus | None = None
    packaging: ReleasePackaging | None = None
    text_language: str | None = None
    text_script: str | None = None
    release_set: ReleaseSetUpdate | None = None
    release_tracks: list[ReleaseTrackUpdate] = field(default_factory=list)
    labels: list[LabelUpdate] = field(default_factory=list)
    track_count: int | None = None
    media_formats: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ReleaseCandidate:
    """Candidate release summary for enrichment selection."""

    mbid: Mbid
    title: str | None = None
    release_date: PartialDate | None = None
    status: ReleaseStatus | None = None
    packaging: ReleasePackaging | None = None
    country: CountryCode | None = None
    release_set_mbid: Mbid | None = None
    artist_names: list[str] = field(default_factory=list)
    track_count: int | None = None
    media_formats: list[str] = field(default_factory=list)
