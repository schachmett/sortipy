"""Ports for ingest-pipeline-specific persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from sortipy.domain.ports.unit_of_work import RepositoryCollection, UnitOfWork

if TYPE_CHECKING:
    from sortipy.domain.ingest_pipeline.context import NormalizationData
    from sortipy.domain.ingest_pipeline.entity_ops import NormKey, NormKeySeq
    from sortipy.domain.model import EntityType, IdentifiedEntity
    from sortipy.domain.ports.persistence import (
        ArtistRepository,
        PlayEventRepository,
        RecordingRepository,
        ReleaseRepository,
        ReleaseSetRepository,
    )


@runtime_checkable
class NormalizationSidecarRepository(Protocol):
    """Persistence contract for normalized dedup keys."""

    def save(self, entity: IdentifiedEntity, data: NormalizationData[IdentifiedEntity]) -> None:
        """Upsert normalization sidecar for ``entity`` using the provided normalized data."""
        ...

    def find_by_keys(
        self,
        entity_type: EntityType,
        keys: NormKeySeq,
    ) -> dict[NormKey, IdentifiedEntity]:
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
    normalization_sidecars: NormalizationSidecarRepository


type IngestUnitOfWork = UnitOfWork[IngestRepositories]
