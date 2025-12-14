"""Intra-ingest deduplication phase."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sortipy.domain.ingest_pipeline.entity_ops import ops_for
from sortipy.domain.ingest_pipeline.orchestrator import PipelineContext, PipelinePhase
from sortipy.domain.types import CanonicalEntity

if TYPE_CHECKING:
    from sortipy.domain.ingest_pipeline.orchestrator import IngestGraph
    from sortipy.domain.ingest_pipeline.state import NormalizationState, deterministic_key


class DeduplicationPhase(PipelinePhase):
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
        key_index: dict[deterministic_key, TEntity] = {}
        survivors: list[TEntity] = []
        collapsed = 0

        for entity in entities:
            if self._deduplicate_entity(entity, state, key_index):
                collapsed += 1
            else:
                survivors.append(entity)

        entities[:] = survivors
        return collapsed

    def _deduplicate_entity[TEntity: CanonicalEntity](
        self,
        entity: TEntity,
        state: NormalizationState,
        key_index: dict[deterministic_key, TEntity],
    ) -> bool:
        """Return False if the entity is new and survives. Return True if it was deduplicated."""
        ops = ops_for(entity)

        keys = state.priority_keys_for(entity)
        if not keys:
            return False

        primary = None
        for key in keys:
            candidate = key_index.get(key)
            if candidate is not None and candidate is not entity:
                primary = candidate
                break
        else:
            _register_keys(key_index, entity, keys)
            return False

        ops.merge(primary, entity)
        ops.rewire(primary, entity)
        state.remove(entity)
        # data = ops.normalize(primary, state)
        # state.store(primary, data)
        # _register_keys(key_index, primary, data.priority_keys)
        # collapsed += 1
        return True


def _register_keys[TEntity: CanonicalEntity](
    mapping: dict[deterministic_key, TEntity],
    entity: TEntity,
    keys: tuple[deterministic_key, ...],
) -> None:
    for key in keys:
        mapping[key] = entity
