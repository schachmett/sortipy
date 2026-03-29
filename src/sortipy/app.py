"""Application orchestration entry points."""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from sortipy.adapters.lastfm import fetch_play_events, should_cache_recent_tracks
from sortipy.adapters.musicbrainz import (
    fetch_release_candidates_from_artist,
    fetch_release_candidates_from_recording,
    fetch_release_candidates_from_release_set,
    fetch_release_graph,
)
from sortipy.adapters.spotify import fetch_library_items
from sortipy.adapters.sqlalchemy import create_unit_of_work_factory
from sortipy.application import (
    LibraryItemIngestRequest,
    PlayEventIngestRequest,
    ingest_library_items,
    ingest_play_events,
    reconcile_release_updates,
)
from sortipy.config import (
    get_database_config,
    get_lastfm_config,
    get_musicbrainz_config,
    get_spotify_config,
    get_sync_config,
)
from sortipy.domain.model import Provider, User

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime
    from uuid import UUID

    from sortipy.adapters.musicbrainz import (
        MusicBrainzReleaseCandidate,
        MusicBrainzReleaseGraphFetchResult,
    )
    from sortipy.application import (
        LibraryItemIngestResult,
        PlayEventIngestResult,
        ReleaseUpdateResult,
    )
    from sortipy.domain.model import Artist, Recording, ReleaseSet
    from sortipy.domain.ports import LibraryItemFetchResult, PlayEventFetchResult
    from sortipy.domain.reconciliation import ManualReviewItem


log = getLogger(__name__)


def _log_manual_review_items(
    *,
    workflow: str,
    items: Iterable[ManualReviewItem],
    skip_reasons: frozenset[str] = frozenset(),
) -> None:
    for item in items:
        if item.reason in skip_reasons:
            continue
        blocked_by = ",".join(str(claim_id) for claim_id in item.blocked_by_claim_ids) or "-"
        candidates = ",".join(str(entity_id) for entity_id in item.candidate_entity_ids) or "-"
        log.warning(
            f"{workflow} manual review: claim_id={item.claim_id} "
            f"subject={item.subject} kind={item.kind} reason={item.reason or '-'} "
            f"blocked_by={blocked_by} candidate_entity_ids={candidates}"
        )


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


def reconcile_lastfm_play_events(
    *,
    user_id: UUID,
    batch_size: int | None = None,
    max_events: int | None = None,
    from_timestamp: datetime | None = None,
    to_timestamp: datetime | None = None,
) -> PlayEventIngestResult:
    """Reconcile Last.fm play events using the configured adapters."""

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
        "Starting Last.fm reconciliation: batch_size=%s, max_events=%s, from=%s, to=%s",
        effective_batch_size,
        max_events,
        from_timestamp,
        to_timestamp,
    )

    result = ingest_play_events(
        request=PlayEventIngestRequest(
            batch_size=effective_batch_size,
            max_events=max_events,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
        ),
        fetcher=_fetcher,
        user=user,
        unit_of_work_factory=unit_of_work_factory,
        source=Provider.LASTFM,
    )
    _log_manual_review_items(workflow="Last.fm", items=result.manual_review_items)

    log.info(
        "Finished Last.fm reconciliation: stored=%s, fetched=%s, catalog_entities=%s, "
        "sidecars=%s, manual_reviews=%s",
        result.stored_events,
        result.fetched,
        result.persisted_entities,
        result.persisted_sidecars,
        len(result.manual_review_items),
    )
    return result


def reconcile_spotify_library_items(
    *,
    user_id: UUID,
    batch_size: int | None = None,
    max_tracks: int | None = None,
    max_albums: int | None = None,
    max_artists: int | None = None,
) -> LibraryItemIngestResult:
    """Reconcile Spotify library items using the configured adapters."""

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
        "Starting Spotify reconciliation: batch_size=%s, max_tracks=%s, "
        "max_albums=%s, max_artists=%s",
        effective_batch_size,
        max_tracks,
        max_albums,
        max_artists,
    )

    result = ingest_library_items(
        request=LibraryItemIngestRequest(
            batch_size=effective_batch_size,
            max_tracks=max_tracks,
            max_albums=max_albums,
            max_artists=max_artists,
        ),
        fetcher=_fetcher,
        unit_of_work_factory=unit_of_work_factory,
        user=user,
        source=Provider.SPOTIFY,
    )
    _log_manual_review_items(workflow="Spotify", items=result.manual_review_items)

    log.info(
        "Finished Spotify reconciliation: stored=%s, skipped=%s, fetched=%s, "
        "catalog_entities=%s, sidecars=%s, manual_reviews=%s",
        result.stored_items,
        result.skipped_existing,
        result.fetched,
        result.persisted_entities,
        result.persisted_sidecars,
        len(result.manual_review_items),
    )
    return result


def reconcile_musicbrainz_releases(
    *,
    limit: int | None = None,
) -> ReleaseUpdateResult:
    """Reconcile MusicBrainz release graphs into the configured catalog."""

    musicbrainz_config = get_musicbrainz_config()
    database_config = get_database_config()
    unit_of_work_factory = create_unit_of_work_factory(database_uri=database_config.uri)

    def _from_recording(recording: Recording) -> list[MusicBrainzReleaseCandidate]:
        return fetch_release_candidates_from_recording(
            recording,
            config=musicbrainz_config,
        )

    def _from_release_set(release_set: ReleaseSet) -> list[MusicBrainzReleaseCandidate]:
        return fetch_release_candidates_from_release_set(
            release_set,
            config=musicbrainz_config,
        )

    def _from_artist(artist: Artist) -> list[MusicBrainzReleaseCandidate]:
        return fetch_release_candidates_from_artist(
            artist,
            config=musicbrainz_config,
        )

    def _fetch_graph(candidate: MusicBrainzReleaseCandidate) -> MusicBrainzReleaseGraphFetchResult:
        return fetch_release_graph(
            candidate,
            config=musicbrainz_config,
        )

    log.info("Starting MusicBrainz reconciliation: limit=%s", limit)
    result = reconcile_release_updates(
        fetch_release_graph=_fetch_graph,
        fetch_candidates_from_recording=_from_recording,
        fetch_candidates_from_release_set=_from_release_set,
        fetch_candidates_from_artist=_from_artist,
        unit_of_work_factory=unit_of_work_factory,
        limit=limit,
        source=Provider.MUSICBRAINZ,
    )
    _log_manual_review_items(
        workflow="MusicBrainz",
        items=result.manual_review_items,
        skip_reasons=frozenset({"musicbrainz_anchor_mismatch"}),
    )
    log.info(
        "Finished MusicBrainz reconciliation: candidates=%s, fetched=%s, applied=%s, "
        "anchors=%s, manual_reviews=%s",
        result.candidate_releases,
        result.fetched_updates,
        result.applied_releases,
        result.anchor_mismatches,
        len(result.manual_review_items),
    )
    return result
