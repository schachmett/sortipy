"""Application orchestration entry points."""

from __future__ import annotations

from dataclasses import dataclass
from logging import getLogger
from typing import TYPE_CHECKING

from sortipy.adapters.lastfm import fetch_play_events, should_cache_recent_tracks
from sortipy.adapters.musicbrainz import (
    fetch_release_candidates_from_artist,
    fetch_release_candidates_from_recording,
    fetch_release_candidates_from_release_set,
    fetch_release_update,
)
from sortipy.adapters.spotify import fetch_library_items
from sortipy.adapters.sqlalchemy import create_unit_of_work_factory
from sortipy.config import (
    get_database_config,
    get_lastfm_config,
    get_musicbrainz_config,
    get_spotify_config,
    get_sync_config,
)
from sortipy.domain.data_integration import (
    LibraryItemSyncRequest,
    PlayEventSyncRequest,
    sync_library_items,
    sync_play_events,
)
from sortipy.domain.entity_updates import apply_release_update, resolve_release_candidate
from sortipy.domain.model import Provider, User

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime
    from uuid import UUID

    from sortipy.domain.data_integration import (
        SyncLibraryItemsResult,
        SyncPlayEventsResult,
    )
    from sortipy.domain.entity_updates import ReleaseCandidate
    from sortipy.domain.model import Artist, Recording, Release, ReleaseSet
    from sortipy.domain.ports import LibraryItemFetchResult, PlayEventFetchResult


log = getLogger(__name__)


@dataclass(slots=True)
class ReleaseEnrichmentResult:
    candidates: int
    updates: int
    applied: int


def create_user(
    *,
    display_name: str,
    email: str | None = None,
    lastfm_user: str | None = None,
    spotify_user_id: str | None = None,
) -> User:
    """Create and persist a user via the configured database."""

    database_config = get_database_config()
    unit_of_work_factory = create_unit_of_work_factory(database_uri=database_config.uri)
    user = User(
        display_name=display_name,
        email=email,
        lastfm_user=lastfm_user,
        spotify_user_id=spotify_user_id,
    )
    with unit_of_work_factory() as uow:
        uow.repositories.users.add(user)
        uow.commit()
    return user


def load_user(*, user_id: UUID) -> User:
    """Load an existing user from the configured database."""

    database_config = get_database_config()
    unit_of_work_factory = create_unit_of_work_factory(database_uri=database_config.uri)
    with unit_of_work_factory() as uow:
        user = uow.repositories.users.get(user_id)
    if user is None:
        raise ValueError(f"User {user_id} not found")
    return user


def sync_lastfm_play_events(
    *,
    user_id: UUID,
    batch_size: int | None = None,
    max_events: int | None = None,
    from_timestamp: datetime | None = None,
    to_timestamp: datetime | None = None,
) -> SyncPlayEventsResult:
    """Synchronise Last.fm play events using the configured adapters."""

    user = load_user(user_id=user_id)
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
    user_id: UUID,
    batch_size: int | None = None,
    max_tracks: int | None = None,
    max_albums: int | None = None,
    max_artists: int | None = None,
) -> SyncLibraryItemsResult:
    """Synchronise Spotify library items using the configured adapters."""

    user = load_user(user_id=user_id)
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


def enrich_musicbrainz_releases(
    *,
    limit: int | None = None,
) -> ReleaseEnrichmentResult:
    """Enrich releases using MusicBrainz data."""

    musicbrainz_config = get_musicbrainz_config()
    database_config = get_database_config()
    unit_of_work_factory = create_unit_of_work_factory(database_uri=database_config.uri)

    with unit_of_work_factory() as uow:
        releases = uow.repositories.releases.list()
        candidates = _select_release_candidates(releases, limit=limit)
        if not candidates:
            return ReleaseEnrichmentResult(candidates=0, updates=0, applied=0)

        def _from_recording(recording: Recording) -> list[ReleaseCandidate]:
            return fetch_release_candidates_from_recording(
                recording,
                config=musicbrainz_config,
            )

        def _from_release_set(release_set: ReleaseSet) -> list[ReleaseCandidate]:
            return fetch_release_candidates_from_release_set(
                release_set,
                config=musicbrainz_config,
            )

        def _from_artist(artist: Artist) -> list[ReleaseCandidate]:
            return fetch_release_candidates_from_artist(
                artist,
                config=musicbrainz_config,
            )

        updates = 0
        applied = 0

        for release in candidates:
            candidate = resolve_release_candidate(
                release,
                fetch_candidates_from_recording=_from_recording,
                fetch_candidates_from_release_set=_from_release_set,
                fetch_candidates_from_artist=_from_artist,
            )
            if candidate is None:
                continue
            update = fetch_release_update(candidate, config=musicbrainz_config)
            updates += 1
            apply_release_update(release, update)
            applied += 1
        uow.commit()

    return ReleaseEnrichmentResult(
        candidates=len(candidates),
        updates=updates,
        applied=applied,
    )


def _select_release_candidates(
    releases: Iterable[Release],
    *,
    limit: int | None = None,
) -> list[Release]:
    candidates: list[Release] = []
    for release in releases:
        if _has_musicbrainz_source(release):
            continue
        candidates.append(release)
        if limit is not None and len(candidates) >= limit:
            break
    return candidates


def _has_musicbrainz_source(release: Release) -> bool:
    provenance = release.provenance
    if provenance is None:
        return False
    return Provider.MUSICBRAINZ in provenance.sources
