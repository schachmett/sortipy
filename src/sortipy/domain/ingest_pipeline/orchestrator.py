"""Phase-based orchestrator for the Sortipy ingest pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from sortipy.domain.types import (
    Artist,
    CanonicalEntity,
    PlayEvent,
    Recording,
    Release,
    ReleaseSet,
    Track,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sortipy.domain.ingest_pipeline.state import NormalizationState


@dataclass(slots=True)
class PipelineContext:
    """Mutable context shared across pipeline phases."""

    batch_id: str | None = None
    normalization_state: NormalizationState | None = None
    normalized_entities_count: int = 0
    dedup_collapsed: int = 0


@dataclass(slots=True)
class IngestGraph:
    """Container for all entities ingested in a single batch run.

    The graph mirrors the structure described in ``docs/data_pipeline.md`` and
    is intentionally lightweight: each phase mutates entities in-place rather
    than creating parallel structures. Keeping the lists explicit also makes it
    trivial to run per-entity-type passes when normalizing or deduplicating.
    """

    artists: list[Artist] = field(default_factory=list[Artist])
    release_sets: list[ReleaseSet] = field(default_factory=list[ReleaseSet])
    releases: list[Release] = field(default_factory=list[Release])
    recordings: list[Recording] = field(default_factory=list[Recording])
    tracks: list[Track] = field(default_factory=list[Track])
    play_events: list[PlayEvent] = field(default_factory=list[PlayEvent])

    def iter_catalog_entities(self) -> Iterable[CanonicalEntity]:
        """Yield all catalog entities (artists through tracks) in dependency order.

        Artists are yielded first so downstream phases can assume their canonical
        identities exist before processing release sets, releases, recordings,
        and tracks. Play events are intentionally skipped because they are the
        leaf nodes of the graph.
        """

        yield from self.artists
        yield from self.release_sets
        yield from self.releases
        yield from self.recordings
        yield from self.tracks


@runtime_checkable
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
    """Utility for constructing a graph from parsed play events.

    The helper only wires the top-level collections; relationship wiring happens
    when adapters (for example the Last.fm translator) attach entities to each
    other as they parse payloads. Having a function for graph construction
    clarifies that *all* events of a batch must share the same graph instance.
    """

    graph = IngestGraph()
    for event in events:
        graph.play_events.append(event)
        if event.track is not None and event.track not in graph.tracks:
            graph.tracks.append(event.track)
        if event.recording not in graph.recordings:
            graph.recordings.append(event.recording)
        for artist_link in event.recording.artists:
            artist = artist_link.artist
            if artist not in graph.artists:
                graph.artists.append(artist)
        track = event.track
        if track is not None:
            release = track.release
            if release not in graph.releases:
                graph.releases.append(release)
            release_set = release.release_set
            if release_set not in graph.release_sets:
                graph.release_sets.append(release_set)
    return graph
