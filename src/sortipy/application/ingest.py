"""Application services for workflow-owned ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sortipy.domain.model import (
    Artist,
    Label,
    Recording,
    Release,
    ReleaseSet,
    ReleaseTrack,
)
from sortipy.domain.reconciliation import ApplyCounters, ReconciliationEngine

from .claim_graphs import build_catalog_claim_graph

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from datetime import datetime

    from sortipy.domain.model import CatalogEntity, EntityType, PlayEvent, Provider, User
    from sortipy.domain.ports.fetching import (
        LibraryItemFetcher,
        LibraryItemFetchResult,
        PlayEventFetcher,
    )
    from sortipy.domain.ports.persistence import PlayEventRepository
    from sortipy.domain.reconciliation import ApplyResult, ManualReviewItem, RepresentativesByClaim
    from sortipy.domain.reconciliation.persist import ReconciliationUnitOfWork

    from .claim_graphs import CatalogGraphBuildResult


@dataclass(slots=True)
class IngestRunResult:
    """Base result for one reconciliation-backed application workflow."""

    fetched: int
    persisted_entities: int
    persisted_sidecars: int
    entities: ApplyCounters
    associations: ApplyCounters
    links: ApplyCounters
    manual_review_items: list[ManualReviewItem]


@dataclass(slots=True)
class PlayEventIngestRequest:
    batch_size: int
    max_events: int | None = None
    from_timestamp: datetime | None = None
    to_timestamp: datetime | None = None


@dataclass(slots=True)
class PlayEventIngestResult(IngestRunResult):
    stored_events: int
    latest_timestamp: datetime | None = None
    now_playing: PlayEvent | None = None


@dataclass(slots=True)
class LibraryItemIngestRequest:
    batch_size: int
    max_tracks: int | None = None
    max_albums: int | None = None
    max_artists: int | None = None


@dataclass(slots=True)
class LibraryItemIngestResult(IngestRunResult):
    stored_items: int
    skipped_existing: int


def ingest_play_events(
    *,
    request: PlayEventIngestRequest,
    fetcher: PlayEventFetcher,
    user: User,
    unit_of_work_factory: Callable[[], ReconciliationUnitOfWork],
    source: Provider,
    engine: ReconciliationEngine | None = None,
) -> PlayEventIngestResult:
    """Fetch, reconcile, rebind, and persist play events."""

    active_engine = engine or ReconciliationEngine.default()
    fetched = 0
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
            return PlayEventIngestResult(
                fetched=fetched,
                persisted_entities=0,
                persisted_sidecars=0,
                entities=_zero_counters(),
                associations=_zero_counters(),
                links=_zero_counters(),
                manual_review_items=[],
                stored_events=0,
                latest_timestamp=latest_seen or effective_cutoff,
                now_playing=result.now_playing,
            )

        graph_result = build_catalog_claim_graph(
            roots=tuple(dict.fromkeys(event.recording for event in new_events)),
            source=source,
        )
        prepared = active_engine.prepare(
            graph_result.graph,
            repositories=uow.repositories,
        )
        executed = active_engine.execute(prepared, uow=uow)

        for event in new_events:
            _rebind_play_event(
                event,
                graph_result=graph_result,
                apply_result=executed.apply_result,
                representatives_by_claim=executed.prepared.representatives_by_claim,
            )
            uow.repositories.play_events.add(event)
        uow.commit()

        return PlayEventIngestResult(
            fetched=fetched,
            persisted_entities=executed.persistence_result.persisted_entities,
            persisted_sidecars=executed.persistence_result.persisted_sidecars,
            entities=executed.apply_result.entities,
            associations=executed.apply_result.associations,
            links=executed.apply_result.links,
            manual_review_items=list(executed.apply_result.manual_review_items),
            stored_events=len(new_events),
            latest_timestamp=latest_seen or effective_cutoff,
            now_playing=result.now_playing,
        )


def ingest_library_items(
    *,
    request: LibraryItemIngestRequest,
    fetcher: LibraryItemFetcher,
    unit_of_work_factory: Callable[[], ReconciliationUnitOfWork],
    user: User,
    source: Provider,
    engine: ReconciliationEngine | None = None,
) -> LibraryItemIngestResult:
    """Fetch, reconcile, rebind, and persist library items."""

    active_engine = engine or ReconciliationEngine.default()

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
            return LibraryItemIngestResult(
                fetched=0,
                persisted_entities=0,
                persisted_sidecars=0,
                entities=_zero_counters(),
                associations=_zero_counters(),
                links=_zero_counters(),
                manual_review_items=[],
                stored_items=0,
                skipped_existing=0,
            )

        graph_result = build_catalog_claim_graph(
            roots=tuple(
                dict.fromkeys(_require_catalog_entity(item.require_target()) for item in items)
            ),
            source=source,
        )
        prepared = active_engine.prepare(
            graph_result.graph,
            repositories=uow.repositories,
        )
        executed = active_engine.execute(prepared, uow=uow)

        stored_items = 0
        skipped_existing = 0
        seen_targets: set[tuple[EntityType, object]] = set()
        for item in items:
            target = graph_result.require_materialized_entity(
                _require_catalog_entity(item.require_target()),
                apply_result=executed.apply_result,
                representatives_by_claim=executed.prepared.representatives_by_claim,
            )
            item.user.retarget_library_item(item, target)
            dedupe_key = (item.target_type, item.target_id)
            if dedupe_key in seen_targets or uow.repositories.library_items.exists(
                user_id=item.user.id,
                target_type=item.target_type,
                target_id=item.target_id,
            ):
                skipped_existing += 1
                continue
            seen_targets.add(dedupe_key)
            uow.repositories.library_items.add(item)
            stored_items += 1

        if stored_items:
            uow.commit()

        return LibraryItemIngestResult(
            fetched=fetched,
            persisted_entities=executed.persistence_result.persisted_entities,
            persisted_sidecars=executed.persistence_result.persisted_sidecars,
            entities=executed.apply_result.entities,
            associations=executed.apply_result.associations,
            links=executed.apply_result.links,
            manual_review_items=list(executed.apply_result.manual_review_items),
            stored_items=stored_items,
            skipped_existing=skipped_existing,
        )


def _rebind_play_event(
    event: PlayEvent,
    *,
    graph_result: CatalogGraphBuildResult,
    apply_result: ApplyResult,
    representatives_by_claim: RepresentativesByClaim,
) -> None:
    if event.track is not None:
        materialized_track = graph_result.require_materialized_association(
            event.track,
            apply_result=apply_result,
            representatives_by_claim=representatives_by_claim,
        )
        if not isinstance(materialized_track, ReleaseTrack):
            raise TypeError(
                f"Expected materialized ReleaseTrack, got {type(materialized_track).__name__}"
            )
        event.user.rebind_play_event(
            event,
            recording=materialized_track.recording,
            track=materialized_track,
        )
        return

    materialized_recording = graph_result.require_materialized_entity(
        event.recording,
        apply_result=apply_result,
        representatives_by_claim=representatives_by_claim,
    )
    if not isinstance(materialized_recording, Recording):
        raise TypeError(
            f"Expected materialized Recording, got {type(materialized_recording).__name__}"
        )
    event.user.rebind_play_event(event, recording=materialized_recording)


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


def _require_catalog_entity(entity: object) -> CatalogEntity:
    if not isinstance(entity, Artist | Label | Recording | Release | ReleaseSet):
        raise TypeError(f"Expected catalog entity, got {type(entity).__name__}")
    return entity


def _zero_counters() -> ApplyCounters:
    return ApplyCounters()
