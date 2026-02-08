"""Association objects.

Owned by aggregate roots.

Only `ReleaseTrack` is externally identifiable today (tracks can have MBIDs).
Contributions do not carry external IDs for now.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from .enums import EntityType
from .external_ids import ExternallyIdentifiableMixin
from .provenance import ProvenanceTrackedMixin

if TYPE_CHECKING:
    from .enums import ArtistRole
    from .music import Artist, Recording, Release, ReleaseSet
    from .primitives import DurationMs


@dataclass(eq=False, kw_only=True)
class _ArtistContribution(ProvenanceTrackedMixin):
    _artist: Artist = field(repr=False)

    role: ArtistRole | None = None
    credit_order: int | None = None
    credited_as: str | None = None
    join_phrase: str | None = None

    @property
    def artist(self) -> Artist:
        return self._artist


@dataclass(eq=False, kw_only=True)
class ReleaseSetContribution(_ArtistContribution):
    ENTITY_TYPE: ClassVar[EntityType] = EntityType.RELEASE_SET_CONTRIBUTION

    _release_set: ReleaseSet = field(repr=False)

    @property
    def release_set(self) -> ReleaseSet:
        return self._release_set


@dataclass(eq=False, kw_only=True)
class RecordingContribution(_ArtistContribution):
    ENTITY_TYPE: ClassVar[EntityType] = EntityType.RECORDING_CONTRIBUTION

    _recording: Recording = field(repr=False)

    @property
    def recording(self) -> Recording:
        return self._recording


@dataclass(eq=False, kw_only=True)
class ReleaseTrack(ProvenanceTrackedMixin, ExternallyIdentifiableMixin):
    """Placement of a recording on a specific release (tracklist entry)."""

    ENTITY_TYPE: ClassVar[EntityType] = EntityType.RELEASE_TRACK

    _release: Release = field(repr=False)
    _recording: Recording = field(repr=False)

    disc_number: int | None = None
    track_number: int | None = None
    title_override: str | None = None
    duration_ms: DurationMs | None = None

    @property
    def release(self) -> Release:
        return self._release

    @property
    def recording(self) -> Recording:
        return self._recording
