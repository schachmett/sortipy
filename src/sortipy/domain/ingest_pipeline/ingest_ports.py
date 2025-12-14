"""Ports for ingest-pipeline-specific persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from sortipy.domain.ports.unit_of_work import RepositoryCollection, UnitOfWork

if TYPE_CHECKING:
    from sortipy.domain.ingest_pipeline.state import NormalizationData
    from sortipy.domain.ports.persistence import (
        ArtistRepository,
        PlayEventRepository,
        RecordingRepository,
        ReleaseRepository,
        ReleaseSetRepository,
        TrackRepository,
    )
    from sortipy.domain.types import CanonicalEntity, CanonicalEntityType


@runtime_checkable
class NormalizationSidecarRepository(Protocol):
    """Persistence contract for normalized dedup keys."""

    def save(self, entity: CanonicalEntity, data: NormalizationData[CanonicalEntity]) -> None:
        """Upsert normalization sidecar for ``entity`` using the provided normalized data."""
        ...

    def find_by_keys(
        self,
        entity_type: CanonicalEntityType,
        keys: tuple[tuple[object, ...], ...],
    ) -> dict[tuple[object, ...], CanonicalEntity]:
        """Return any existing entities matching the supplied deterministic keys."""
        ...


@dataclass(slots=True)
class IngestRepositories(RepositoryCollection):
    """Repositories required for ingest pipeline phases (and play events)."""

    play_events: PlayEventRepository
    artists: ArtistRepository
    release_sets: ReleaseSetRepository
    releases: ReleaseRepository
    recordings: RecordingRepository
    tracks: TrackRepository
    normalization_sidecars: NormalizationSidecarRepository


type IngestUnitOfWork = UnitOfWork[IngestRepositories]
