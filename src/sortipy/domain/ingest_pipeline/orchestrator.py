"""Phase-based orchestrator for the Sortipy ingest pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from sortipy.domain.ingest_pipeline.context import IngestGraph, PipelineContext

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sortipy.domain.model import PlayEvent


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


def ingest_graph_from_events(events: Iterable[PlayEvent]) -> IngestGraph:
    """Utility for constructing a graph from domain.model PlayEvents.

    The helper only wires the top-level collections; relationship wiring happens
    when adapters (for example the Last.fm translator) attach entities to each
    other as they parse payloads. Having a function for graph construction
    clarifies that *all* events of a batch must share the same graph instance.
    """

    graph = IngestGraph()
    for event in events:
        graph.add_play_event(event)
        graph.add_user(event.user)
        graph.add_recording(event.recording)

        for artist in event.recording.artists:
            graph.add_artist(artist)

        if event.track is None:
            continue

        graph.add_release(event.track.release)
        graph.add_release_set(event.track.release.release_set)
        for artist in event.track.release.release_set.artists:
            graph.add_artist(artist)

    return graph
