"""Shared context structures for the ingest pipeline (graph + state)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, overload

from sortipy.domain.model import (
    Artist,
    EntityType,
    IdentifiedEntity,
    PlayEvent,
    Recording,
    Release,
    ReleaseSet,
    User,
)

if TYPE_CHECKING:
    from sortipy.domain.ingest_pipeline.entity_ops import (
        ArtistNormalizationData,
        RecordingNormalizationData,
        ReleaseNormalizationData,
        ReleaseSetNormalizationData,
    )
    from sortipy.domain.ingest_pipeline.ingest_ports import IngestUnitOfWork


type NormKey = tuple[object, ...]
type NormKeySeq = tuple[NormKey, ...]


class NormalizationData[TEntity: IdentifiedEntity](Protocol):
    """Structured normalization metadata with deterministic keys."""

    priority_keys: NormKeySeq


@dataclass(slots=True)
class NormalizationState:
    """Registry of normalization metadata keyed by entity identity."""

    storage: dict[EntityType, dict[int, NormalizationData[Any]]] = field(
        default_factory=dict[EntityType, dict[int, NormalizationData[Any]]]
    )
    priority_key_map: dict[int, NormKeySeq] = field(default_factory=dict[int, NormKeySeq])

    def store[TEntity: IdentifiedEntity](
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
    def fetch[TEntity: IdentifiedEntity](
        self, entity: TEntity
    ) -> NormalizationData[TEntity] | None: ...
    def fetch[TEntity: IdentifiedEntity](
        self, entity: TEntity
    ) -> NormalizationData[TEntity] | None:
        bucket = self._bucket(entity.entity_type)
        data = bucket.get(id(entity))
        if data is None:
            return None
        return data

    def remove(self, entity: IdentifiedEntity) -> None:
        bucket = self._bucket(entity.entity_type)
        key = id(entity)
        bucket.pop(key, None)
        self.priority_key_map.pop(key, None)

    def _bucket(self, entity_type: EntityType) -> dict[int, NormalizationData[Any]]:
        if entity_type not in self.storage:
            self.storage[entity_type] = {}
        return self.storage[entity_type]

    def priority_keys_for(self, entity: object) -> NormKeySeq | None:
        return self.priority_key_map.get(id(entity))

    def primary_key_for(self, entity: object) -> NormKey | None:
        keys = self.priority_keys_for(entity)
        if not keys:
            return None
        return keys[0]


@dataclass(slots=True)
class PipelineContext:
    """Mutable context shared across pipeline phases."""

    batch_id: str | None = None
    normalization_state: NormalizationState | None = None
    ingest_uow: IngestUnitOfWork | None = None
    normalized_entities_count: int = 0
    dedup_collapsed: int = 0


@dataclass(slots=True)
class IngestGraph:
    """Container for all domain.model entities ingested in a single batch run.

    The graph mirrors the structure described in ``docs/data_pipeline.md`` and
    is intentionally lightweight: each phase mutates entities in-place rather
    than creating parallel structures. Keeping the lists explicit also makes it
    trivial to run per-entity-type passes when normalizing or deduplicating.
    """

    artists: list[Artist] = field(default_factory=list[Artist])
    release_sets: list[ReleaseSet] = field(default_factory=list[ReleaseSet])
    releases: list[Release] = field(default_factory=list[Release])
    recordings: list[Recording] = field(default_factory=list[Recording])
    users: list[User] = field(default_factory=list[User])
    play_events: list[PlayEvent] = field(default_factory=list[PlayEvent])

    def add_artist(self, artist: Artist) -> None:
        if artist not in self.artists:
            self.artists.append(artist)

    def add_release_set(self, release_set: ReleaseSet) -> None:
        if release_set not in self.release_sets:
            self.release_sets.append(release_set)

    def add_release(self, release: Release) -> None:
        if release not in self.releases:
            self.releases.append(release)

    def add_recording(self, recording: Recording) -> None:
        if recording not in self.recordings:
            self.recordings.append(recording)

    def add_user(self, user: User) -> None:
        if user not in self.users:
            self.users.append(user)

    def add_play_event(self, play_event: PlayEvent) -> None:
        if play_event not in self.play_events:
            self.play_events.append(play_event)
