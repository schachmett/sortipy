"""Public domain model surface."""

from __future__ import annotations

from .associations import (
    RecordingContribution,
    ReleaseSetContribution,
    ReleaseTrack,
)
from .audit import EntityMerge
from .entity import Entity, IdentifiedEntity
from .enums import (
    ArtistRole,
    EntityType,
    ExternalNamespace,
    MergeReason,
    Provider,
    ReleaseSetType,
)
from .external_ids import (
    ExternalID,
    ExternalIdCollection,
    ExternallyIdentifiable,
    Namespace,
    provider_for,
)
from .music import Artist, Label, Recording, Release, ReleaseSet
from .primitives import (
    Barcode,
    CatalogNumber,
    CountryCode,
    DurationMs,
    Isrc,
    Mbid,
    PartialDate,
)
from .provenance import Provenance, Provenanced, ProvenanceTracked
from .user import LibraryItem, PlayEvent, User

__all__ = [  # noqa: RUF022
    # base
    "IdentifiedEntity",
    "Entity",
    # external ids
    "ExternalID",
    "Namespace",
    "ExternalIdCollection",
    "provider_for",
    "ExternallyIdentifiable",
    # provenance
    "Provenance",
    "Provenanced",
    "ProvenanceTracked",
    # associations
    "ReleaseSetContribution",
    "RecordingContribution",
    "ReleaseTrack",
    # music
    "Artist",
    "ReleaseSet",
    "Release",
    "Recording",
    "Label",
    # user
    "User",
    "LibraryItem",
    "PlayEvent",
    # audit
    "EntityMerge",
    # enums
    "ArtistRole",
    "EntityType",
    "ExternalNamespace",
    "MergeReason",
    "Provider",
    "ReleaseSetType",
    # primitives
    "Barcode",
    "CatalogNumber",
    "CountryCode",
    "DurationMs",
    "Isrc",
    "Mbid",
    "PartialDate",
]
