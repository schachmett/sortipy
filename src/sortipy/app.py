"""Application orchestration entry points."""

from __future__ import annotations

from collections.abc import Callable
from logging import getLogger
from typing import TYPE_CHECKING

from sortipy.adapters.lastfm import build_http_lastfm_fetcher
from sortipy.adapters.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork, startup
from sortipy.domain.data_integration import SyncPlayEventsResult, sync_play_events
from sortipy.domain.ports.unit_of_work import PlayEventUnitOfWork

if TYPE_CHECKING:
    from datetime import datetime

    from sortipy.domain.ports.fetching import PlayEventFetcher

UnitOfWorkFactory = Callable[[], PlayEventUnitOfWork]


log = getLogger(__name__)


def sync_lastfm_play_events(
    *,
    source: PlayEventFetcher | None = None,
    unit_of_work_factory: UnitOfWorkFactory | None = None,
    batch_size: int = 200,
    max_events: int | None = None,
    from_timestamp: datetime | None = None,
    to_timestamp: datetime | None = None,
) -> SyncPlayEventsResult:
    """Synchronise Last.fm play events using the configured adapters."""

    startup()
    effective_source = source or build_http_lastfm_fetcher()
    effective_uow = unit_of_work_factory or SqlAlchemyUnitOfWork
    log.info(
        "Starting Last.fm sync: batch_size=%s, max_events=%s, from=%s, to=%s",
        batch_size,
        max_events,
        from_timestamp,
        to_timestamp,
    )

    result = sync_play_events(
        fetcher=effective_source,
        unit_of_work_factory=effective_uow,
        batch_size=batch_size,
        max_events=max_events,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
    )

    log.info(
        f"Finished Last.fm sync: stored={result.stored}, fetched={result.fetched}, "
        f"latest={result.latest_timestamp}, now_playing={bool(result.now_playing)}"
    )

    return result
