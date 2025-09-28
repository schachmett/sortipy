"""Ports and use cases for integrating scrobble data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Callable, Iterable, Protocol  # noqa: UP035

if TYPE_CHECKING:
    from types import TracebackType

    from sortipy.domain.types import Scrobble


@dataclass
class FetchScrobblesResult:
    """Snapshot of a paged Last.fm scrobble response."""

    scrobbles: Iterable[Scrobble]
    page: int
    total_pages: int
    now_playing: Scrobble | None = None


class LastFmScrobbleSource(Protocol):
    """Port for retrieving Last.fm scrobbles."""

    def fetch_recent(
        self,
        *,
        page: int = 1,
        limit: int = 200,
        from_ts: int | None = None,
        to_ts: int | None = None,
        extended: bool = False,
    ) -> FetchScrobblesResult:
        """Return a page of the most recent scrobbles for a user."""
        ...


class ScrobbleRepository(Protocol):
    """Persistence port for storing scrobbles."""

    def add(self, scrobble: Scrobble) -> None:
        """Persist a scrobble instance."""
        ...

    def exists(self, timestamp: datetime) -> bool:
        """Return whether a scrobble at the given timestamp already exists."""
        ...

    def latest_timestamp(self) -> datetime | None:
        """Return the most recent scrobble timestamp in the store."""
        ...


class ScrobbleUnitOfWork(Protocol):
    """Transaction boundary for scrobble related persistence."""

    scrobbles: ScrobbleRepository

    def __enter__(self) -> ScrobbleUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@dataclass
class SyncScrobblesResult:
    """Outcome of a sync operation."""

    stored: int
    pages_processed: int
    latest_timestamp: datetime | None
    now_playing: Scrobble | None


@dataclass
class SyncRequest:
    """Parameters controlling a sync invocation."""

    limit: int = 200
    start_page: int = 1
    max_pages: int | None = None
    from_timestamp: datetime | None = None
    to_timestamp: datetime | None = None
    extended: bool = False


@dataclass
class SyncScrobbles:
    """Application service for synchronising Last.fm scrobbles into storage."""

    source: LastFmScrobbleSource
    unit_of_work: Callable[[], ScrobbleUnitOfWork]

    def run(self, request: SyncRequest | None = None) -> SyncScrobblesResult:
        """Fetch scrobbles and persist them, returning a sync summary."""

        params = request or SyncRequest()
        pages_processed = 0
        stored = 0
        latest_seen: datetime | None = None
        now_playing: Scrobble | None = None
        effective_cutoff: datetime | None = params.from_timestamp

        with self.unit_of_work() as uow:
            if effective_cutoff is None:
                effective_cutoff = uow.scrobbles.latest_timestamp()

            from_ts_epoch = _to_epoch_seconds(effective_cutoff) + 1 if effective_cutoff else None
            to_ts_epoch = _to_epoch_seconds(params.to_timestamp) if params.to_timestamp else None

            page = params.start_page
            while True:
                result = self.source.fetch_recent(
                    page=page,
                    limit=params.limit,
                    from_ts=from_ts_epoch,
                    to_ts=to_ts_epoch,
                    extended=params.extended,
                )
                pages_processed += 1
                now_playing = now_playing or result.now_playing

                new_scrobbles, newest_in_page = self._filter_new_scrobbles(
                    result.scrobbles,
                    effective_cutoff,
                    params.to_timestamp,
                    uow.scrobbles,
                )
                if newest_in_page:
                    latest_seen = max(latest_seen or newest_in_page, newest_in_page)

                stored += self._persist_scrobbles(uow, new_scrobbles)

                if self._should_stop(params, pages_processed, page, result.total_pages):
                    break
                page += 1
                # After the first page the `from` constraint is no longer required.
                from_ts_epoch = None

        return SyncScrobblesResult(
            stored=stored,
            pages_processed=pages_processed,
            latest_timestamp=latest_seen or effective_cutoff,
            now_playing=now_playing,
        )

    def _filter_new_scrobbles(
        self,
        scrobbles: Iterable[Scrobble],
        cutoff: datetime | None,
        upper: datetime | None,
        repository: ScrobbleRepository,
    ) -> tuple[list[Scrobble], datetime | None]:
        newest: datetime | None = None
        fresh: list[Scrobble] = []
        for scrobble in scrobbles:
            if cutoff and scrobble.timestamp <= cutoff:
                continue
            if upper and scrobble.timestamp > upper:
                continue
            if repository.exists(scrobble.timestamp):
                continue
            fresh.append(scrobble)
            newest = max(newest or scrobble.timestamp, scrobble.timestamp)
        return fresh, newest

    def _persist_scrobbles(self, uow: ScrobbleUnitOfWork, scrobbles: list[Scrobble]) -> int:
        if not scrobbles:
            return 0
        for scrobble in scrobbles:
            uow.scrobbles.add(scrobble)
        uow.commit()
        return len(scrobbles)

    @staticmethod
    def _should_stop(
        params: SyncRequest,
        pages_processed: int,
        current_page: int,
        total_pages: int,
    ) -> bool:
        if params.max_pages is not None and pages_processed >= params.max_pages:
            return True
        return current_page >= total_pages


def _to_epoch_seconds(value: datetime | None) -> int:
    if value is None:
        raise ValueError("Cannot convert None to epoch seconds")
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp())
