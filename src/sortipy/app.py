"""Application orchestration entry points."""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from sortipy.adapters.lastfm import fetch_play_events, should_cache_recent_tracks
from sortipy.adapters.spotify import fetch_library_items
from sortipy.adapters.sqlalchemy import create_unit_of_work_factory
from sortipy.config import (
    get_database_config,
    get_lastfm_config,
    get_spotify_config,
    get_sync_config,
)
from sortipy.domain.data_integration import (
    LibraryItemSyncRequest,
    PlayEventSyncRequest,
    SyncLibraryItemsResult,
    SyncPlayEventsResult,
    sync_library_items,
    sync_play_events,
)

if TYPE_CHECKING:
    from datetime import datetime

    from sortipy.domain.model import User
    from sortipy.domain.ports import LibraryItemFetchResult, PlayEventFetchResult


log = getLogger(__name__)


def sync_lastfm_play_events(
    *,
    user: User,
    batch_size: int | None = None,
    max_events: int | None = None,
    from_timestamp: datetime | None = None,
    to_timestamp: datetime | None = None,
) -> SyncPlayEventsResult:
    """Synchronise Last.fm play events using the configured adapters."""

    lastfm_config = get_lastfm_config(cache_predicate=should_cache_recent_tracks)
    sync_config = get_sync_config()
    database_config = get_database_config()
    unit_of_work_factory = create_unit_of_work_factory(database_uri=database_config.uri)
    effective_batch_size = sync_config.play_event_batch_size if batch_size is None else batch_size

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
        effective_batch_size,
        max_events,
        from_timestamp,
        to_timestamp,
    )

    request = PlayEventSyncRequest(
        batch_size=effective_batch_size,
        max_events=max_events,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
    )
    result = sync_play_events(
        request=request,
        fetcher=_fetcher,
        user=user,
        unit_of_work_factory=unit_of_work_factory,
    )

    log.info(
        f"Finished Last.fm sync: stored={result.stored}, fetched={result.fetched}, "
        f"latest={result.latest_timestamp}, now_playing={bool(result.now_playing)}"
    )

    return result


def sync_spotify_library_items(
    *,
    user: User,
    batch_size: int | None = None,
    max_tracks: int | None = None,
    max_albums: int | None = None,
    max_artists: int | None = None,
) -> SyncLibraryItemsResult:
    """Synchronise Spotify library items using the configured adapters."""

    spotify_config = get_spotify_config()
    sync_config = get_sync_config()
    database_config = get_database_config()
    unit_of_work_factory = create_unit_of_work_factory(database_uri=database_config.uri)
    effective_batch_size = sync_config.library_item_batch_size if batch_size is None else batch_size

    def _fetcher(
        *,
        user: User,
        batch_size: int = 50,
        max_tracks: int | None = None,
        max_albums: int | None = None,
        max_artists: int | None = None,
    ) -> LibraryItemFetchResult:
        return fetch_library_items(
            config=spotify_config,
            user=user,
            batch_size=batch_size,
            max_tracks=max_tracks,
            max_albums=max_albums,
            max_artists=max_artists,
        )

    log.info(
        (
            "Starting Spotify library sync: "
            "batch_size=%s, max_tracks=%s, max_albums=%s, max_artists=%s"
        ),
        effective_batch_size,
        max_tracks,
        max_albums,
        max_artists,
    )

    request = LibraryItemSyncRequest(
        batch_size=effective_batch_size,
        max_tracks=max_tracks,
        max_albums=max_albums,
        max_artists=max_artists,
    )
    result = sync_library_items(
        request=request,
        fetcher=_fetcher,
        unit_of_work_factory=unit_of_work_factory,
        user=user,
    )

    log.info(
        "Finished Spotify library sync: stored=%s, fetched=%s",
        result.stored,
        result.fetched,
    )

    return result
