"""Intra-ingest deduplication phase."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from sortipy.domain.ingest_pipeline.entity_ops import ops_for
from sortipy.domain.ingest_pipeline.orchestrator import PipelineContext, PipelinePhase
from sortipy.domain.types import CanonicalEntity

if TYPE_CHECKING:
    from sortipy.domain.ingest_pipeline.orchestrator import IngestGraph
    from sortipy.domain.ingest_pipeline.state import NormalizationState

TEntity = TypeVar("TEntity", bound=CanonicalEntity)


class DefaultDeduplicationPhase(PipelinePhase):
    """Coordinates intra-batch deduplication once normalization finished."""

    name: str = "deduplication"

    def run(self, graph: IngestGraph, *, context: PipelineContext) -> None:
        state = context.normalization_state
        if state is None:
            raise RuntimeError("Normalization must run before deduplication")

        context.dedup_collapsed += self._deduplicate_entities(graph.artists, state)
        context.dedup_collapsed += self._deduplicate_entities(graph.release_sets, state)
        context.dedup_collapsed += self._deduplicate_entities(graph.releases, state)
        context.dedup_collapsed += self._deduplicate_entities(graph.recordings, state)
        context.dedup_collapsed += self._deduplicate_entities(graph.tracks, state)

    def _deduplicate_entities[TEntity: CanonicalEntity](
        self,
        entities: list[TEntity],
        state: NormalizationState,
    ) -> int:
        if not entities:
            return 0

        ops = ops_for(entities[0])
        key_index: dict[tuple[object, ...], TEntity] = {}
        survivors: list[TEntity] = []
        collapsed = 0

        for entity in entities:
            keys = state.priority_keys_for(entity)
            if not keys:
                survivors.append(entity)
                continue

            primary: TEntity | None = None
            for key in keys:
                candidate = key_index.get(key)
                if candidate is not None and candidate is not entity:
                    primary = candidate
                    break

            if primary is None:
                _register_keys(key_index, entity, keys)
                survivors.append(entity)
                continue

            ops.merge(primary, entity)
            ops.rewire(primary, entity)
            state.remove(entity)
            data = ops.normalize(primary, state)
            state.store(primary, data)
            primary_keys = state.priority_keys_for(primary)
            if primary_keys:
                _register_keys(key_index, primary, primary_keys)
            collapsed += 1

        entities[:] = survivors
        return collapsed


def _register_keys[TEntity: CanonicalEntity](
    mapping: dict[tuple[object, ...], TEntity],
    entity: TEntity,
    keys: tuple[tuple[object, ...], ...],
) -> None:
    for key in keys:
        mapping[key] = entity
