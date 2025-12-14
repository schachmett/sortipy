"""Shared normalization sidecar structures for the ingest pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, overload

from sortipy.domain.types import CanonicalEntity, CanonicalEntityType

if TYPE_CHECKING:
    from sortipy.domain.ingest_pipeline.entity_ops import (
        ArtistNormalizationData,
        RecordingNormalizationData,
        ReleaseNormalizationData,
        ReleaseSetNormalizationData,
        TrackNormalizationData,
    )
    from sortipy.domain.types import Artist, Recording, Release, ReleaseSet, Track

type deterministic_key = tuple[object, ...]


class NormalizationData[TEntity: CanonicalEntity](Protocol):
    """Structured normalization metadata with deterministic keys."""

    priority_keys: tuple[deterministic_key, ...]


@dataclass(slots=True)
class NormalizationState:
    """Registry of normalization metadata keyed by entity identity."""

    storage: dict[CanonicalEntityType, dict[int, NormalizationData[Any]]] = field(
        default_factory=dict[CanonicalEntityType, dict[int, NormalizationData[Any]]]
    )
    priority_key_map: dict[int, tuple[deterministic_key, ...]] = field(
        default_factory=dict[int, tuple[deterministic_key, ...]]
    )

    def store[TEntity: CanonicalEntity](
        self, entity: TEntity, data: NormalizationData[TEntity]
    ) -> None:
        bucket = self._bucket(entity.entity_type)
        key = id(entity)
        bucket[key] = data
        if data.priority_keys:
            self.priority_key_map[key] = data.priority_keys

    @overload
    def fetch(self, entity: Artist) -> ArtistNormalizationData | None: ...
    @overload
    def fetch(self, entity: ReleaseSet) -> ReleaseSetNormalizationData | None: ...
    @overload
    def fetch(self, entity: Release) -> ReleaseNormalizationData | None: ...
    @overload
    def fetch(self, entity: Recording) -> RecordingNormalizationData | None: ...
    @overload
    def fetch(self, entity: Track) -> TrackNormalizationData | None: ...
    @overload
    def fetch[TEntity: CanonicalEntity](
        self, entity: TEntity
    ) -> NormalizationData[TEntity] | None: ...
    def fetch[TEntity: CanonicalEntity](self, entity: TEntity) -> NormalizationData[TEntity] | None:
        bucket = self._bucket(entity.entity_type)
        data = bucket.get(id(entity))
        if data is None:
            return None
        return data

    def remove(self, entity: CanonicalEntity) -> None:
        bucket = self._bucket(entity.entity_type)
        key = id(entity)
        bucket.pop(key, None)
        self.priority_key_map.pop(key, None)

    def _bucket(self, entity_type: CanonicalEntityType) -> dict[int, NormalizationData[Any]]:
        if entity_type not in self.storage:
            self.storage[entity_type] = {}
        return self.storage[entity_type]

    def priority_keys_for(self, entity: object) -> tuple[deterministic_key, ...] | None:
        return self.priority_key_map.get(id(entity))

    def primary_key_for(self, entity: object) -> deterministic_key | None:
        keys = self.priority_keys_for(entity)
        if not keys:
            return None
        return keys[0]
