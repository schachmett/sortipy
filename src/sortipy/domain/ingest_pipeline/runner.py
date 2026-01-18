"""Entry points for running the ingest pipeline and building ingest graphs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sortipy.domain.model import Artist, LibraryItem, Recording, Release, ReleaseSet

from .canonicalization import CanonicalizationPhase
from .context import EntityCounters, IngestGraph, PipelineContext
from .deduplication import DeduplicationPhase
from .normalization import NormalizationPhase
from .orchestrator import IngestionPipeline

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sortipy.domain.model import PlayEvent

    from .ingest_ports import IngestionUnitOfWork


def run_ingest_pipeline(*, graph: IngestGraph, uow: IngestionUnitOfWork) -> EntityCounters:
    """Run the default ingestion pipeline for ``graph`` and return counters."""

    context = PipelineContext(ingest_uow=uow)
    pipeline = IngestionPipeline(
        phases=(NormalizationPhase(), DeduplicationPhase(), CanonicalizationPhase())
    )
    pipeline.run(graph, context=context)
    return context.counters


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


def ingest_graph_from_library_items(items: Iterable[LibraryItem]) -> IngestGraph:
    """Construct a graph from library items with hydrated targets."""

    graph = IngestGraph()
    for item in items:
        graph.add_user(item.user)
        target = item.require_target()

        if isinstance(target, Artist):
            _add_artist_graph(graph, target)
        elif isinstance(target, ReleaseSet):
            _add_release_set_graph(graph, target)
        elif isinstance(target, Release):
            _add_release_graph(graph, target)
        elif isinstance(target, Recording):
            _add_recording_graph(graph, target)
        else:
            raise ValueError(  # noqa: TRY004
                f"Unsupported LibraryItem target: {target.entity_type} ({type(target).__name__})"
            )

    return graph


def _add_artist_graph(graph: IngestGraph, artist: Artist) -> None:
    graph.add_artist(artist)


def _add_release_set_graph(graph: IngestGraph, release_set: ReleaseSet) -> None:
    graph.add_release_set(release_set)
    for artist in release_set.artists:
        graph.add_artist(artist)
    for release in release_set.releases:
        graph.add_release(release)
        for track in release.tracks:
            graph.add_recording(track.recording)
            for artist in track.recording.artists:
                graph.add_artist(artist)


def _add_release_graph(graph: IngestGraph, release: Release) -> None:
    graph.add_release(release)
    graph.add_release_set(release.release_set)
    for artist in release.release_set.artists:
        graph.add_artist(artist)
    for track in release.tracks:
        graph.add_recording(track.recording)
        for artist in track.recording.artists:
            graph.add_artist(artist)


def _add_recording_graph(graph: IngestGraph, recording: Recording) -> None:
    graph.add_recording(recording)
    for artist in recording.artists:
        graph.add_artist(artist)
    for track in recording.release_tracks:
        graph.add_release(track.release)
        graph.add_release_set(track.release.release_set)
        for artist in track.release.release_set.artists:
            graph.add_artist(artist)
