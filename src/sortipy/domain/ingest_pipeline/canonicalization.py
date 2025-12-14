"""Canonicalization phase implementation."""

from __future__ import annotations

from dataclasses import dataclass
from logging import getLogger
from typing import TYPE_CHECKING, cast

from sortipy.domain.ingest_pipeline.entity_ops import EntityOps, ops_for
from sortipy.domain.ingest_pipeline.orchestrator import PipelineContext, PipelinePhase
from sortipy.domain.types import CanonicalEntity

if TYPE_CHECKING:
    from sortipy.domain.ingest_pipeline.ingest_ports import NormalizationSidecarRepository
    from sortipy.domain.ingest_pipeline.orchestrator import IngestGraph
    from sortipy.domain.ingest_pipeline.state import NormalizationData, NormalizationState
    from sortipy.domain.ports.persistence import CanonicalEntityRepository


log = getLogger(__name__)


@dataclass(slots=True)
class _Resolver[TEntity: CanonicalEntity]:
    """Resolve a single ingest entity against the canonical catalog."""

    entity: TEntity
    data: NormalizationData[TEntity]
    repo: CanonicalEntityRepository[TEntity]
    sidecars: NormalizationSidecarRepository
    ops: EntityOps[TEntity]

    def resolve(self) -> TEntity:
        # Keep MBIDs as the first deterministic key even though external IDs are tried first;
        # sidecars store only key tuples, so MBID-in-keys still enables exact matches when
        # the current entity lacks external_ids or only sidecar data is available.
        found = self._match_external_ids()
        if found is not None:
            return found

        found = self._match_keys()
        if found is not None:
            return found

        self._persist_new()
        return self.entity

    def _match_external_ids(self) -> TEntity | None:
        for external_id in self.entity.external_ids:
            existing = self.repo.get_by_external_id(external_id.namespace, external_id.value)
            if existing is None:
                continue
            self._merge_into(existing)
            return existing
        return None

    def _match_keys(self) -> TEntity | None:
        matches = self.sidecars.find_by_keys(self.entity.entity_type, self.data.priority_keys)
        candidates: list[TEntity] = []
        for key in self.data.priority_keys:
            candidate = matches.get(key)
            if candidate is None:
                continue
            typed_candidate = cast(TEntity, candidate)
            if typed_candidate not in candidates:
                candidates.append(typed_candidate)

        if not candidates:
            return None

        if len(candidates) > 1:
            log.warning(
                "Ambiguous deterministic match for %s: %d candidates", self.entity, len(candidates)
            )
            return None

        target = candidates[0]
        self._merge_into(target)
        return target

    def _merge_into(self, target: TEntity) -> None:
        if target is self.entity:
            return
        self.ops.merge(target, self.entity)
        self.ops.rewire(target, self.entity)
        self.sidecars.save(target, self.data)

    def _persist_new(self) -> None:
        self.repo.add(self.entity)
        self.sidecars.save(self.entity, self.data)


@dataclass(slots=True)
class CanonicalizationPhase(PipelinePhase):
    """Resolve normalized ingest entities against the canonical catalog."""

    name: str = "canonicalization"

    def run(self, graph: IngestGraph, *, context: PipelineContext) -> None:
        state = context.normalization_state
        if state is None:
            raise RuntimeError("Normalization state required for canonicalization")

        uow = context.ingest_uow
        if uow is None:
            raise RuntimeError("IngestUnitOfWork required for canonicalization")

        repos = uow.repositories
        sidecars = repos.normalization_sidecars
        _resolve_entities(graph.artists, state, repos.artists, sidecars)
        _resolve_entities(graph.release_sets, state, repos.release_sets, sidecars)
        _resolve_entities(graph.releases, state, repos.releases, sidecars)
        _resolve_entities(graph.recordings, state, repos.recordings, sidecars)
        _resolve_entities(graph.tracks, state, repos.tracks, sidecars)
        uow.commit()


def _resolve_entities[TEntity: CanonicalEntity](
    entities: list[TEntity],
    state: NormalizationState,
    repo: CanonicalEntityRepository[TEntity],
    sidecars: NormalizationSidecarRepository,
) -> None:
    if not entities:
        return
    ops = ops_for(entities[0])
    for index, entity in enumerate(entities):
        data = state.fetch(entity)
        if data is None:
            raise RuntimeError("NormalizationData missing in Canonicalization phase")
        entities[index] = _Resolver(entity, data, repo, sidecars, ops).resolve()
