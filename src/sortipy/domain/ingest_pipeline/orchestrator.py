"""Phase-based orchestrator for the Sortipy ingest pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from .context import IngestGraph, PipelineContext

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence



class PipelinePhase(Protocol):
    """Contract implemented by each ingestion phase."""

    name: str

    def run(self, graph: IngestGraph, *, context: PipelineContext) -> None: ...


@dataclass(slots=True)
class IngestionPipeline:
    """Compose and execute the ordered pipeline phases.

    The orchestrator is intentionally simple: it wires phases together and
    guarantees order-of-operations matches the documentation in
    ``docs/data_pipeline.md``.
    """

    phases: Sequence[PipelinePhase] = field(default_factory=tuple)

    def with_phase(self, phase: PipelinePhase) -> IngestionPipeline:
        """Return a new pipeline appending ``phase`` at the end."""

        return IngestionPipeline(phases=(*self.phases, phase))

    def extend(self, phases: Iterable[PipelinePhase]) -> IngestionPipeline:
        """Return a new pipeline with the provided ``phases`` concatenated."""

        return IngestionPipeline(phases=(*self.phases, *tuple(phases)))

    def run(self, graph: IngestGraph, *, context: PipelineContext | None = None) -> IngestGraph:
        """Execute the configured phases in-order against ``graph``."""

        active_context = context or PipelineContext()
        for phase in self.phases:
            phase.run(graph, context=active_context)
        return graph

