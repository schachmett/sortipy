"""Ports and services for ingesting listening history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from datetime import datetime
    from types import TracebackType

    from sortipy.domain.types import PlayEvent


@dataclass
class FetchPlayEventsResult:
    """Container for a batch of play events returned by a source."""

    events: Iterable[PlayEvent]
    now_playing: PlayEvent | None = None


class PlayEventSource(Protocol):
    """Port for retrieving play events from an external provider."""

    def fetch_recent(
        self,
        *,
        batch_size: int = 200,
        since: datetime | None = None,
        until: datetime | None = None,
        max_events: int | None = None,
    ) -> FetchPlayEventsResult:
        """Return recent play events, honouring optional temporal bounds."""
        ...


class PlayEventRepository(Protocol):
    """Persistence port for storing play events."""

    def add(self, event: PlayEvent) -> None:
        """Persist a play event instance."""
        ...

    def exists(self, timestamp: datetime) -> bool:
        """Return whether a play event at the given timestamp already exists."""
        ...

    def latest_timestamp(self) -> datetime | None:
        """Return the most recent play event timestamp seen so far."""
        ...


class PlayEventUnitOfWork(Protocol):
    """Transaction boundary for play-event persistence operations."""

    play_events: PlayEventRepository

    def __enter__(self) -> PlayEventUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@dataclass
class SyncPlayEventsResult:
    """Outcome of a play-event sync operation."""

    stored: int
    fetched: int
    latest_timestamp: datetime | None
    now_playing: PlayEvent | None


@dataclass
class SyncRequest:
    """Parameters controlling a sync invocation."""

    batch_size: int = 200
    max_events: int | None = None
    from_timestamp: datetime | None = None
    to_timestamp: datetime | None = None


@dataclass
class SyncPlayEvents:
    """Application service for synchronising play events into storage."""

    source: PlayEventSource
    unit_of_work: Callable[[], PlayEventUnitOfWork]

    def run(self, request: SyncRequest | None = None) -> SyncPlayEventsResult:
        """Fetch play events and persist them, returning a sync summary."""

        params = request or SyncRequest()
        fetched = 0
        stored = 0
        latest_seen: datetime | None = None
        effective_cutoff: datetime | None = params.from_timestamp

        result: FetchPlayEventsResult | None = None

        with self.unit_of_work() as uow:
            if effective_cutoff is None:
                effective_cutoff = uow.play_events.latest_timestamp()

            result = self.source.fetch_recent(
                batch_size=params.batch_size,
                since=effective_cutoff,
                until=params.to_timestamp,
                max_events=params.max_events,
            )

            events = list(result.events)
            fetched = len(events)

            new_events, newest_observed = self._filter_new_events(
                events,
                effective_cutoff,
                params.to_timestamp,
                uow.play_events,
            )

            if newest_observed is not None:
                latest_seen = max(latest_seen or newest_observed, newest_observed)

            stored += self._persist_events(uow, new_events)

        if result is None:
            raise RuntimeError("Play event source did not return a result")

        return SyncPlayEventsResult(
            stored=stored,
            fetched=fetched,
            latest_timestamp=latest_seen or effective_cutoff,
            now_playing=result.now_playing,
        )

    def _filter_new_events(
        self,
        events: Iterable[PlayEvent],
        cutoff: datetime | None,
        upper: datetime | None,
        repository: PlayEventRepository,
    ) -> tuple[list[PlayEvent], datetime | None]:
        newest: datetime | None = None
        fresh: list[PlayEvent] = []
        for event in events:
            if cutoff and event.timestamp <= cutoff:
                continue
            if upper and event.timestamp > upper:
                continue
            if repository.exists(event.timestamp):
                continue
            fresh.append(event)
            newest = max(newest or event.timestamp, event.timestamp)
        return fresh, newest

    def _persist_events(self, uow: PlayEventUnitOfWork, events: list[PlayEvent]) -> int:
        if not events:
            return 0
        for event in events:
            uow.play_events.add(event)
        uow.commit()
        return len(events)


__all__ = [
    "FetchPlayEventsResult",
    "PlayEventRepository",
    "PlayEventSource",
    "PlayEventUnitOfWork",
    "SyncPlayEvents",
    "SyncPlayEventsResult",
    "SyncRequest",
]
