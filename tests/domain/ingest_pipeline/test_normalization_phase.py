from __future__ import annotations

from datetime import UTC, datetime

from sortipy.domain.ingest_pipeline.context import PipelineContext
from sortipy.domain.ingest_pipeline.normalization import NormalizationPhase
from sortipy.domain.ingest_pipeline.runner import ingest_graph_from_events
from tests.helpers.play_events import make_play_event


def test_normalization_populates_state_and_counts_entities() -> None:
    event = make_play_event("Normalization Track", timestamp=datetime(2024, 1, 1, tzinfo=UTC))
    graph = ingest_graph_from_events([event])
    context = PipelineContext()

    NormalizationPhase().run(graph, context=context)

    state = context.normalization_state
    assert state is not None

    expected_count = {
        entity_type: count
        for entity_type, count in (
            (graph.artists[0].entity_type, len(graph.artists)),
            (graph.release_sets[0].entity_type, len(graph.release_sets)),
            (graph.releases[0].entity_type, len(graph.releases)),
            (graph.recordings[0].entity_type, len(graph.recordings)),
            (graph.users[0].entity_type, len(graph.users)),
            (graph.play_events[0].entity_type, len(graph.play_events)),
        )
        if count
    }
    assert context.counters.normalized == expected_count

    for entity in graph.artists:
        assert state.fetch(entity) is not None
    for entity in graph.release_sets:
        assert state.fetch(entity) is not None
    for entity in graph.releases:
        assert state.fetch(entity) is not None
    for entity in graph.recordings:
        assert state.fetch(entity) is not None
    for entity in graph.users:
        assert state.fetch(entity) is not None
    for entity in graph.play_events:
        assert state.fetch(entity) is not None
