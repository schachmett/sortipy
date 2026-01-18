"""Normalization phase implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .context import NormalizationState, PipelineContext
from .entity_ops import ops_for
from .orchestrator import PipelinePhase

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sortipy.domain.model import IdentifiedEntity

    from .context import IngestGraph


class NormalizationPhase(PipelinePhase):
    """Coordinates normalization across all entity types in the ingest graph."""

    name: str = "normalization"

    def run(self, graph: IngestGraph, *, context: PipelineContext) -> None:
        state = context.normalization_state or NormalizationState()
        context.normalization_state = state

        self._normalize_batch(graph.artists, state, context=context)
        self._normalize_batch(graph.release_sets, state, context=context)
        self._normalize_batch(graph.releases, state, context=context)
        self._normalize_batch(graph.recordings, state, context=context)
        self._normalize_batch(graph.users, state, context=context)
        self._normalize_batch(graph.play_events, state, context=context)

    def _normalize_batch(
        self,
        entities: Iterable[IdentifiedEntity],
        state: NormalizationState,
        *,
        context: PipelineContext,
    ) -> None:
        for entity in entities:
            ops = ops_for(entity)
            data = ops.normalize(entity, state)
            state.store(entity, data)
            context.counters.bump_normalized(entity.entity_type)
