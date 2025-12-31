"""Application services for ingesting listening history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sortipy.domain.ingest_pipeline import (
    CanonicalizationPhase,
    DeduplicationPhase,
    IngestionPipeline,
    NormalizationPhase,
)
from sortipy.domain.ingest_pipeline.context import IngestGraph, PipelineContext
from sortipy.domain.ingest_pipeline.orchestrator import ingest_graph_from_events

DEFAULT_SYNC_BATCH_SIZE = 200

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from datetime import datetime

    from sortipy.domain.ingest_pipeline.ingest_ports import IngestUnitOfWork
    from sortipy.domain.model import PlayEvent
    from sortipy.domain.ports.fetching import PlayEventFetcher, PlayEventFetchResult
    from sortipy.domain.ports.persistence import PlayEventRepository


@dataclass(slots=True)
class SyncPlayEventsResult:
    """Outcome of a play-event sync operation."""

    stored: int
    fetched: int
    latest_timestamp: datetime | None
    now_playing: PlayEvent | None


def sync_play_events(
    *,
    fetcher: PlayEventFetcher,
    unit_of_work_factory: Callable[[], IngestUnitOfWork],
    batch_size: int = DEFAULT_SYNC_BATCH_SIZE,
    max_events: int | None = None,
    from_timestamp: datetime | None = None,
    to_timestamp: datetime | None = None,
) -> SyncPlayEventsResult:
    """Fetch play events and persist them, returning a sync summary."""

    fetched = 0
    stored = 0
    latest_seen: datetime | None = None
    effective_cutoff: datetime | None = from_timestamp

    result: PlayEventFetchResult | None = None

    pipeline = IngestionPipeline(
        phases=(NormalizationPhase(), DeduplicationPhase(), CanonicalizationPhase())
    )

    with unit_of_work_factory() as uow:
        repository = uow.repositories.play_events

        if effective_cutoff is None:
            effective_cutoff = repository.latest_timestamp()

        result = fetcher(
            batch_size=batch_size,
            since=effective_cutoff,
            until=to_timestamp,
            max_events=max_events,
        )

        events = list(result.events)
        fetched = len(events)

        new_events, newest_observed = _filter_new_events(
            events,
            effective_cutoff,
            to_timestamp,
            repository,
        )

        if newest_observed is not None:
            latest_seen = max(latest_seen or newest_observed, newest_observed)

        stored += _persist_events(uow, new_events, pipeline)

    if result is None:
        raise RuntimeError("Play event source did not return a result")

    return SyncPlayEventsResult(
        stored=stored,
        fetched=fetched,
        latest_timestamp=latest_seen or effective_cutoff,
        now_playing=result.now_playing,
    )


def _filter_new_events(
    events: Iterable[PlayEvent],
    cutoff: datetime | None,
    upper: datetime | None,
    repository: PlayEventRepository,
) -> tuple[list[PlayEvent], datetime | None]:
    newest: datetime | None = None
    fresh: list[PlayEvent] = []
    seen_timestamps: set[datetime] = set()
    for event in events:
        played_at = event.played_at
        if cutoff and played_at <= cutoff:
            continue
        if upper and played_at > upper:
            continue
        if repository.exists(user_id=event.user.id, source=event.source, played_at=played_at):
            continue
        if played_at in seen_timestamps:
            continue
        fresh.append(event)
        seen_timestamps.add(played_at)
        newest = max(newest or played_at, played_at)
    return fresh, newest


def _persist_events(
    uow: IngestUnitOfWork,
    events: list[PlayEvent],
    pipeline: IngestionPipeline,
) -> int:
    if not events:
        return 0
    graph: IngestGraph = ingest_graph_from_events(events)
    context = PipelineContext(ingest_uow=uow)
    pipeline.run(graph, context=context)
    for event in graph.play_events:
        uow.repositories.play_events.add(event)
    uow.commit()
    return len(events)
