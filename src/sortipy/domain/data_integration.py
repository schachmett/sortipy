"""Application services for ingesting listening history."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sortipy.domain.ingest_pipeline import (
    ingest_graph_from_events,
    ingest_graph_from_library_items,
    run_ingest_pipeline,
)
from sortipy.domain.model import EntityType

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from datetime import datetime

    from sortipy.domain.ingest_pipeline import (
        LibraryItemSyncUnitOfWork,
        PlayEventSyncUnitOfWork,
    )
    from sortipy.domain.model import PlayEvent, User
    from sortipy.domain.ports import (
        LibraryItemFetcher,
        LibraryItemFetchResult,
        PlayEventFetcher,
        PlayEventRepository,
    )


@dataclass(slots=True)
class SyncResult:
    """Outcome of a library-items sync operation."""

    stored: int
    fetched: int
    normalized: dict[EntityType, int] = field(default_factory=dict[EntityType, int])
    dedup_collapsed: dict[EntityType, int] = field(default_factory=dict[EntityType, int])
    persisted_new: dict[EntityType, int] = field(default_factory=dict[EntityType, int])
    merged: dict[EntityType, int] = field(default_factory=dict[EntityType, int])


@dataclass(slots=True)
class SyncPlayEventsResult(SyncResult):
    """Outcome of a play-event sync operation."""

    latest_timestamp: datetime | None = None
    now_playing: PlayEvent | None = None


@dataclass(slots=True)
class SyncLibraryItemsResult(SyncResult):
    """Outcome of a library-items sync operation."""


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
            return SyncPlayEventsResult(
                stored=0,
                fetched=fetched,
                latest_timestamp=latest_seen or effective_cutoff,
                now_playing=result.now_playing,
            )

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
        normalized=counters.normalized if counters else {},
        dedup_collapsed=counters.dedup_collapsed,
        persisted_new=counters.persisted_new,
        merged=counters.merged,
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
                normalized={},
                dedup_collapsed={},
                persisted_new={},
                merged={},
            )

        graph = ingest_graph_from_library_items(items)
        counters = run_ingest_pipeline(graph=graph, uow=uow)
        for item in items:
            uow.repositories.library_items.add(item)
        stored = len(items)
        uow.commit()

    return SyncLibraryItemsResult(
        stored=stored,
        fetched=fetched,
        normalized=counters.normalized,
        dedup_collapsed=counters.dedup_collapsed,
        persisted_new=counters.persisted_new,
        merged=counters.merged,
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
        if repository.exists(event):
            continue
        if played_at in seen_timestamps:
            continue
        fresh.append(event)
        seen_timestamps.add(played_at)
        newest = max(newest or played_at, played_at)
    return fresh, newest
