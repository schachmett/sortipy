"""Application services for ingesting listening history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sortipy.domain.ingest_pipeline import (
    EntityCounters,
    ingest_graph_from_events,
    ingest_graph_from_library_items,
    run_ingest_pipeline,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from datetime import datetime

    from sortipy.domain.ingest_pipeline import (
        LibraryItemSyncUnitOfWork,
        PlayEventSyncUnitOfWork,
    )
    from sortipy.domain.model import LibraryItem, PlayEvent, User
    from sortipy.domain.ports import (
        LibraryItemFetcher,
        LibraryItemFetchResult,
        PlayEventFetcher,
        PlayEventRepository,
    )


@dataclass(slots=True)
class SyncPlayEventsResult:
    """Outcome of a play-event sync operation."""

    stored: int
    fetched: int
    latest_timestamp: datetime | None
    now_playing: PlayEvent | None
    counters: EntityCounters


@dataclass(slots=True)
class SyncLibraryItemsResult:
    """Outcome of a library-items sync operation."""

    stored: int
    fetched: int
    counters: EntityCounters


@dataclass(slots=True)
class PlayEventSyncRequest:
    """Parameters for fetching and filtering play events."""

    batch_size: int
    max_events: int | None = None
    from_timestamp: datetime | None = None
    to_timestamp: datetime | None = None


@dataclass(slots=True)
class LibraryItemSyncRequest:
    """Parameters for fetching library items from providers."""

    batch_size: int
    max_tracks: int | None = None
    max_albums: int | None = None
    max_artists: int | None = None


def sync_play_events(
    *,
    request: PlayEventSyncRequest,
    fetcher: PlayEventFetcher,
    user: User,
    unit_of_work_factory: Callable[[], PlayEventSyncUnitOfWork],
) -> SyncPlayEventsResult:
    """Fetch play events and persist them, returning a sync summary."""

    fetched = 0
    stored = 0
    latest_seen: datetime | None = None
    effective_cutoff: datetime | None = request.from_timestamp

    with unit_of_work_factory() as uow:
        repository = uow.repositories.play_events

        if effective_cutoff is None:
            effective_cutoff = repository.latest_timestamp()

        result = fetcher(
            user=user,
            batch_size=request.batch_size,
            since=effective_cutoff,
            until=request.to_timestamp,
            max_events=request.max_events,
        )

        events = list(result.events)
        fetched = len(events)

        new_events, newest_observed = _filter_new_events(
            events,
            effective_cutoff,
            request.to_timestamp,
            repository,
        )

        if newest_observed is not None:
            latest_seen = max(latest_seen or newest_observed, newest_observed)

        if not new_events:
            counters = EntityCounters()
        else:
            graph = ingest_graph_from_events(new_events)
            counters = run_ingest_pipeline(graph=graph, uow=uow)
            for event in graph.play_events:
                uow.repositories.play_events.add(event)
            uow.commit()
        stored = len(new_events)

    return SyncPlayEventsResult(
        stored=stored,
        fetched=fetched,
        latest_timestamp=latest_seen or effective_cutoff,
        now_playing=result.now_playing,
        counters=counters,
    )


def sync_library_items(
    *,
    request: LibraryItemSyncRequest,
    fetcher: LibraryItemFetcher,
    unit_of_work_factory: Callable[[], LibraryItemSyncUnitOfWork],
    user: User,
) -> SyncLibraryItemsResult:
    """Fetch library items and persist their catalog entities."""

    fetched = 0
    stored = 0

    with unit_of_work_factory() as uow:
        result: LibraryItemFetchResult = fetcher(
            user=user,
            batch_size=request.batch_size,
            max_tracks=request.max_tracks,
            max_albums=request.max_albums,
            max_artists=request.max_artists,
        )
        items = list(result.library_items)
        fetched = len(items)

        if not items:
            return SyncLibraryItemsResult(
                stored=0,
                fetched=0,
                counters=EntityCounters(),
            )

        graph = ingest_graph_from_library_items(items)
        counters = run_ingest_pipeline(graph=graph, uow=uow)
        stored = _persist_library_items(uow, items)
        uow.commit()

    return SyncLibraryItemsResult(stored=stored, fetched=fetched, counters=counters)


def _persist_library_items(
    uow: LibraryItemSyncUnitOfWork,
    items: list[LibraryItem],
) -> int:
    """Persist library items once repository support is added."""

    _ = uow
    # TODO(sortipy): persist library items once repositories exist.  # noqa: FIX002
    return len(items)


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
