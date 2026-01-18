"""Application orchestration entry points."""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from sortipy.adapters.lastfm import fetch_play_events, should_cache_recent_tracks
from sortipy.adapters.sqlalchemy.unit_of_work import create_unit_of_work_factory
from sortipy.config import get_database_config, get_lastfm_config
from sortipy.domain.data_integration import SyncPlayEventsResult, sync_play_events

if TYPE_CHECKING:
    from datetime import datetime

    from sortipy.domain.model import User
    from sortipy.domain.ports.fetching import PlayEventFetchResult


log = getLogger(__name__)


def sync_lastfm_play_events(
    *,
    user: User,
    batch_size: int = 200,
    max_events: int | None = None,
    from_timestamp: datetime | None = None,
    to_timestamp: datetime | None = None,
) -> SyncPlayEventsResult:
    """Synchronise Last.fm play events using the configured adapters."""

    lastfm_config = get_lastfm_config(cache_predicate=should_cache_recent_tracks)
    database_config = get_database_config()
    unit_of_work_factory = create_unit_of_work_factory(database_uri=database_config.uri)

    def _fetcher(
        *,
        user: User,
        batch_size: int = 200,
        since: datetime | None = None,
        until: datetime | None = None,
        max_events: int | None = None,
    ) -> PlayEventFetchResult:
        return fetch_play_events(
            config=lastfm_config,
            user=user,
            batch_size=batch_size,
            since=since,
            until=until,
            max_events=max_events,
        )

    log.info(
        "Starting Last.fm sync: batch_size=%s, max_events=%s, from=%s, to=%s",
        batch_size,
        max_events,
        from_timestamp,
        to_timestamp,
    )

    result = sync_play_events(
        fetcher=_fetcher,
        user=user,
        unit_of_work_factory=unit_of_work_factory,
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
