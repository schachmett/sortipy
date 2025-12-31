from __future__ import annotations

from dataclasses import dataclass

from sortipy.domain.ingest_pipeline.context import IngestGraph, PipelineContext
from sortipy.domain.ingest_pipeline.orchestrator import IngestionPipeline, PipelinePhase


@dataclass(slots=True)
class _RecordingPhase(PipelinePhase):
    name: str
    calls: list[str]

    def run(self, graph: IngestGraph, *, context: PipelineContext) -> None:
        _ = (graph, context)
        self.calls.append(self.name)


def test_pipeline_runs_phases_in_order() -> None:
    calls: list[str] = []
    first = _RecordingPhase(name="first", calls=calls)
    second = _RecordingPhase(name="second", calls=calls)
    pipeline = IngestionPipeline(phases=(first, second))

    pipeline.run(IngestGraph(), context=PipelineContext())

    assert calls == ["first", "second"]
