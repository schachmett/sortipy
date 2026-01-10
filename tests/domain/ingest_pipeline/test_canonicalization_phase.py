from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import pytest

from sortipy.domain.ingest_pipeline import (
    CanonicalizationPhase,
    IngestionPipeline,
    NormalizationPhase,
)
from sortipy.domain.ingest_pipeline.context import (
    IngestGraph,
    NormalizationState,
    NormKey,
    NormKeySeq,
    PipelineContext,
)
from sortipy.domain.ingest_pipeline.entity_ops import normalize_artist
from sortipy.domain.ingest_pipeline.ingest_ports import IngestRepositories
from sortipy.domain.model import (
    Artist,
    EntityType,
    ExternalNamespace,
    IdentifiedEntity,
    PlayEvent,
    Provider,
    Recording,
    Release,
    ReleaseSet,
)
from sortipy.domain.ports.persistence import PlayEventRepository

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from sortipy.domain.ingest_pipeline.context import NormalizationData


def _pipeline() -> IngestionPipeline:
    return IngestionPipeline(
        phases=(
            NormalizationPhase(),
            CanonicalizationPhase(),
        )
    )


@dataclass(slots=True)
class _FakePlayEventRepository(PlayEventRepository):
    def add(self, entity: PlayEvent) -> None:
        _ = entity

    def exists(self, *, user_id: UUID, source: Provider, played_at: datetime) -> bool:
        _ = (user_id, source, played_at)
        return False

    def latest_timestamp(self) -> datetime | None:
        return None


class _FakeCanonicalRepository[TEntity]:
    def __init__(self) -> None:
        self._items: list[TEntity] = []

    def add(self, entity: TEntity) -> None:
        self._items.append(entity)

    def get_by_external_id(self, namespace: object, value: str) -> TEntity | None:
        for entity in self._items:
            external_ids = getattr(entity, "external_ids", ())
            for ext in external_ids:
                if ext.namespace == namespace and ext.value == value:
                    return entity
        return None


class _FakeNormalizationSidecarRepository:
    def __init__(self) -> None:
        self._keys: dict[tuple[EntityType, NormKey], IdentifiedEntity] = {}

    def save(
        self,
        entity: IdentifiedEntity,
        data: NormalizationData[IdentifiedEntity],
    ) -> None:
        if not data.priority_keys:
            return
        entity_type = entity.entity_type
        for key in data.priority_keys:
            self._keys[(entity_type, key)] = entity

    def find_by_keys(
        self,
        entity_type: EntityType,
        keys: NormKeySeq,
    ) -> dict[NormKey, IdentifiedEntity]:
        found: dict[NormKey, IdentifiedEntity] = {}
        for key in keys:
            entity = self._keys.get((entity_type, key))
            if entity is not None:
                found[key] = entity
        return found


class FakeIngestUnitOfWork:
    def __init__(
        self,
        *,
        artists: _FakeCanonicalRepository[Artist] | None = None,
        release_sets: _FakeCanonicalRepository[ReleaseSet] | None = None,
        releases: _FakeCanonicalRepository[Release] | None = None,
        recordings: _FakeCanonicalRepository[Recording] | None = None,
        sidecars: _FakeNormalizationSidecarRepository | None = None,
    ) -> None:
        self.repositories = IngestRepositories(
            play_events=_FakePlayEventRepository(),
            artists=artists or _FakeCanonicalRepository[Artist](),
            release_sets=release_sets or _FakeCanonicalRepository[ReleaseSet](),
            releases=releases or _FakeCanonicalRepository[Release](),
            recordings=recordings or _FakeCanonicalRepository[Recording](),
            normalization_sidecars=sidecars or _FakeNormalizationSidecarRepository(),
        )
        self.committed = False

    def __enter__(self) -> FakeIngestUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> Literal[False]:
        return False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.committed = False


def test_canonicalization_matches_external_id() -> None:
    existing = Artist(name="Radiohead")
    existing.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, "mbid-1")

    repo = _FakeCanonicalRepository[Artist]()
    repo.add(existing)
    sidecars = _FakeNormalizationSidecarRepository()

    ingest_artist = Artist(name="radiohead")
    ingest_artist.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, "mbid-1")

    graph = IngestGraph(artists=[ingest_artist])
    uow = FakeIngestUnitOfWork(artists=repo, sidecars=sidecars)
    context = PipelineContext(ingest_uow=uow)
    _pipeline().run(graph, context=context)

    assert graph.artists[0].id == existing.id
    assert repo._items == [existing]  # pyright: ignore[reportPrivateUsage] # noqa: SLF001


def test_canonicalization_matches_deterministic_keys() -> None:
    existing = Artist(name="Kendrick Lamar")
    sidecar_data = normalize_artist(existing, _state=NormalizationState())

    repo = _FakeCanonicalRepository[Artist]()
    repo.add(existing)
    sidecars = _FakeNormalizationSidecarRepository()
    sidecars.save(existing, sidecar_data)

    ingest_artist = Artist(name="kendrick lamar")
    graph = IngestGraph(artists=[ingest_artist])
    uow = FakeIngestUnitOfWork(artists=repo, sidecars=sidecars)
    context = PipelineContext(ingest_uow=uow)
    _pipeline().run(graph, context=context)

    assert graph.artists[0].id == existing.id


def test_canonicalization_requires_normalization_state() -> None:
    graph = IngestGraph(artists=[Artist(name="Missing State")])
    context = PipelineContext(ingest_uow=FakeIngestUnitOfWork())

    with pytest.raises(RuntimeError, match="Normalization state required"):
        CanonicalizationPhase().run(graph, context=context)


def test_canonicalization_requires_ingest_uow() -> None:
    graph = IngestGraph(artists=[Artist(name="Missing UoW")])
    context = PipelineContext(normalization_state=NormalizationState())

    with pytest.raises(RuntimeError, match="IngestUnitOfWork required"):
        CanonicalizationPhase().run(graph, context=context)
