"""Normalization phase implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sortipy.domain.ingest_pipeline.entity_ops import ops_for
from sortipy.domain.ingest_pipeline.orchestrator import PipelineContext, PipelinePhase
from sortipy.domain.ingest_pipeline.state import NormalizationState

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sortipy.domain.ingest_pipeline.orchestrator import IngestGraph
    from sortipy.domain.types import CanonicalEntity


class NormalizationPhase(PipelinePhase):
    """Coordinates normalization across all entity types in the ingest graph."""

    name: str = "normalization"

    def run(self, graph: IngestGraph, *, context: PipelineContext) -> None:
        state = context.normalization_state or NormalizationState()
        context.normalization_state = state

        context.normalized_entities_count += self._normalize_batch(graph.artists, state)
        context.normalized_entities_count += self._normalize_batch(graph.release_sets, state)
        context.normalized_entities_count += self._normalize_batch(graph.releases, state)
        context.normalized_entities_count += self._normalize_batch(graph.recordings, state)
        context.normalized_entities_count += self._normalize_batch(graph.tracks, state)

    def _normalize_batch(
        self,
        entities: Iterable[CanonicalEntity],
        state: NormalizationState,
    ) -> int:
        count = 0
        for entity in entities:
            ops = ops_for(entity)
            data = ops.normalize(entity, state)
            state.store(entity, data)
            count += 1
        return count
