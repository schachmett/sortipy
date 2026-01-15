"""Ports for ingest-pipeline-specific persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from sortipy.domain.ports.unit_of_work import (
    CatalogRepositories,
    UnitOfWork,
)

if TYPE_CHECKING:
    from sortipy.domain.ingest_pipeline.context import NormalizationData
    from sortipy.domain.ingest_pipeline.entity_ops import NormKey, NormKeySeq
    from sortipy.domain.model import EntityType, IdentifiedEntity
    from sortipy.domain.ports.persistence import LibraryItemRepository, PlayEventRepository


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


@runtime_checkable
class IngestionRepositories(CatalogRepositories, Protocol):
    """Repositories required for ingestion phases."""

    @property
    def normalization_sidecars(self) -> NormalizationSidecarRepository: ...


@runtime_checkable
class PlayEventSyncRepositories(IngestionRepositories, Protocol):
    """Repositories required for play-event sync."""

    @property
    def play_events(self) -> PlayEventRepository: ...


@runtime_checkable
class LibraryItemSyncRepositories(IngestionRepositories, Protocol):
    """Repositories required for library-item sync."""

    @property
    def library_items(self) -> LibraryItemRepository: ...


type IngestionUnitOfWork = UnitOfWork[IngestionRepositories]
type PlayEventSyncUnitOfWork = UnitOfWork[PlayEventSyncRepositories]
type LibraryItemSyncUnitOfWork = UnitOfWork[LibraryItemSyncRepositories]
