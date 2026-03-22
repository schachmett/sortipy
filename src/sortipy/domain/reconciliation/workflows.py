"""Workflow services built on top of the reconciliation core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sortipy.domain.model import (
    Artist,
    EntityType,
    Label,
    Provider,
    Recording,
    Release,
    ReleaseSet,
    ReleaseTrack,
)

from .apply import ApplyCounters
from .catalog import build_catalog_claim_graph
from .contracts import (
    AmbiguousResolution,
    ConflictResolution,
    ManualReviewItem,
    ManualReviewSubject,
    ResolvedResolution,
)
from .factory import create_default_reconciliation_engine
from .release_candidates import resolve_release_candidate

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from datetime import datetime
    from uuid import UUID

    from sortipy.domain.model import CatalogEntity, PlayEvent, User
    from sortipy.domain.ports import (
        LibraryItemFetcher,
        LibraryItemFetchResult,
        PlayEventFetcher,
        ReleaseCandidatesFromArtist,
        ReleaseCandidatesFromRecording,
        ReleaseCandidatesFromReleaseSet,
    )
    from sortipy.domain.ports.enrichment import ReleaseGraphFetcher
    from sortipy.domain.ports.persistence import PlayEventRepository

    from .apply import ApplyResult
    from .catalog import CatalogClaimGraphBundle
    from .contracts import (
        AssociationResolutionsByClaim,
        EntityResolutionsByClaim,
        KeysByClaim,
        LinkResolutionsByClaim,
        RepresentativesByClaim,
    )
    from .engine import ReconciliationEngine
    from .graph import ClaimGraph
    from .persist import PersistenceResult, ReconciliationUnitOfWork
    from .release_candidates import ReleaseSelectionPolicy
    from .resolve import ResolveRepositories


@dataclass(slots=True)
class ReconciliationRunResult:
    """Base workflow result for one reconciliation-backed run."""

    fetched: int
    persisted_entities: int
    persisted_sidecars: int
    entities: ApplyCounters
    associations: ApplyCounters
    links: ApplyCounters
    manual_review_items: list[ManualReviewItem]


@dataclass(slots=True)
class LastfmReconciliationResult(ReconciliationRunResult):
    stored_events: int
    latest_timestamp: datetime | None = None
    now_playing: PlayEvent | None = None


@dataclass(slots=True)
class SpotifyLibraryReconciliationResult(ReconciliationRunResult):
    stored_items: int
    skipped_existing: int


@dataclass(slots=True)
class MusicBrainzReconciliationResult(ReconciliationRunResult):
    candidate_releases: int
    fetched_updates: int
    applied_releases: int
    anchor_mismatches: int


@dataclass(slots=True)
class PlayEventReconciliationRequest:
    batch_size: int
    max_events: int | None = None
    from_timestamp: datetime | None = None
    to_timestamp: datetime | None = None


@dataclass(slots=True)
class LibraryItemReconciliationRequest:
    batch_size: int
    max_tracks: int | None = None
    max_albums: int | None = None
    max_artists: int | None = None


@dataclass(slots=True)
class PreparedCatalogReconciliation:
    """Stage outputs up to and including resolve."""

    bundle: CatalogClaimGraphBundle
    keys_by_claim: KeysByClaim
    deduplicated_graph: ClaimGraph
    representatives_by_claim: RepresentativesByClaim
    entity_resolutions_by_claim: EntityResolutionsByClaim
    association_resolutions_by_claim: AssociationResolutionsByClaim
    link_resolutions_by_claim: LinkResolutionsByClaim


@dataclass(slots=True)
class ExecutedCatalogReconciliation:
    """Full stage outputs for one materialized claim bundle."""

    bundle: CatalogClaimGraphBundle
    representatives_by_claim: RepresentativesByClaim
    apply_result: ApplyResult
    persistence_result: PersistenceResult


def _prepare_catalog_reconciliation(
    bundle: CatalogClaimGraphBundle,
    *,
    repositories: ResolveRepositories,
    engine: ReconciliationEngine,
) -> PreparedCatalogReconciliation:
    keys_by_claim = engine.normalize(bundle.graph)
    deduplicated_graph, representatives_by_claim = engine.deduplicate(
        bundle.graph,
        keys_by_claim=keys_by_claim,
    )
    (
        entity_resolutions_by_claim,
        association_resolutions_by_claim,
        link_resolutions_by_claim,
    ) = engine.resolve(
        deduplicated_graph,
        keys_by_claim=keys_by_claim,
        repositories=repositories,
    )
    return PreparedCatalogReconciliation(
        bundle=bundle,
        keys_by_claim=keys_by_claim,
        deduplicated_graph=deduplicated_graph,
        representatives_by_claim=representatives_by_claim,
        entity_resolutions_by_claim=entity_resolutions_by_claim,
        association_resolutions_by_claim=association_resolutions_by_claim,
        link_resolutions_by_claim=link_resolutions_by_claim,
    )


def _apply_prepared_catalog_reconciliation(
    prepared: PreparedCatalogReconciliation,
    *,
    uow: ReconciliationUnitOfWork,
    engine: ReconciliationEngine,
) -> ExecutedCatalogReconciliation:
    (
        entity_instructions_by_claim,
        association_instructions_by_claim,
        link_instructions_by_claim,
    ) = engine.decide(
        prepared.entity_resolutions_by_claim,
        prepared.association_resolutions_by_claim,
        prepared.link_resolutions_by_claim,
        graph=prepared.deduplicated_graph,
    )
    apply_result = engine.apply(
        prepared.deduplicated_graph,
        entity_instructions_by_claim=entity_instructions_by_claim,
        association_instructions_by_claim=association_instructions_by_claim,
        link_instructions_by_claim=link_instructions_by_claim,
    )
    persistence_result = engine.persist(
        graph=prepared.deduplicated_graph,
        keys_by_claim=prepared.keys_by_claim,
        entity_instructions_by_claim=entity_instructions_by_claim,
        association_instructions_by_claim=association_instructions_by_claim,
        link_instructions_by_claim=link_instructions_by_claim,
        apply_result=apply_result,
        uow=uow,
    )
    return ExecutedCatalogReconciliation(
        bundle=prepared.bundle,
        representatives_by_claim=prepared.representatives_by_claim,
        apply_result=apply_result,
        persistence_result=persistence_result,
    )


def reconcile_play_events(
    *,
    request: PlayEventReconciliationRequest,
    fetcher: PlayEventFetcher,
    user: User,
    unit_of_work_factory: Callable[[], ReconciliationUnitOfWork],
    engine: ReconciliationEngine | None = None,
) -> LastfmReconciliationResult:
    """Fetch play events, reconcile catalog state, and persist rebound events."""

    active_engine = engine or create_default_reconciliation_engine()

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
            return LastfmReconciliationResult(
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

        roots = tuple(dict.fromkeys(event.recording for event in new_events))
        bundle = build_catalog_claim_graph(roots=roots, source=Provider.LASTFM)
        prepared = _prepare_catalog_reconciliation(
            bundle,
            repositories=uow.repositories,
            engine=active_engine,
        )
        executed = _apply_prepared_catalog_reconciliation(
            prepared,
            uow=uow,
            engine=active_engine,
        )

        for event in new_events:
            _rebind_play_event(
                event,
                bundle=executed.bundle,
                apply_result=executed.apply_result,
                representatives_by_claim=executed.representatives_by_claim,
            )
            uow.repositories.play_events.add(event)
        uow.commit()

        return LastfmReconciliationResult(
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


def reconcile_library_items(
    *,
    request: LibraryItemReconciliationRequest,
    fetcher: LibraryItemFetcher,
    unit_of_work_factory: Callable[[], ReconciliationUnitOfWork],
    user: User,
    engine: ReconciliationEngine | None = None,
) -> SpotifyLibraryReconciliationResult:
    """Fetch library items, reconcile catalog state, and persist rebound items."""

    active_engine = engine or create_default_reconciliation_engine()

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
            return SpotifyLibraryReconciliationResult(
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

        roots = tuple(
            dict.fromkeys(_require_catalog_entity(item.require_target()) for item in items)
        )
        bundle = build_catalog_claim_graph(roots=roots, source=Provider.SPOTIFY)
        prepared = _prepare_catalog_reconciliation(
            bundle,
            repositories=uow.repositories,
            engine=active_engine,
        )
        executed = _apply_prepared_catalog_reconciliation(
            prepared,
            uow=uow,
            engine=active_engine,
        )

        stored_items = 0
        skipped_existing = 0
        seen_targets: set[tuple[EntityType, UUID]] = set()
        for item in items:
            target = bundle.require_materialized_entity(
                _require_catalog_entity(item.require_target()),
                apply_result=executed.apply_result,
                representatives_by_claim=executed.representatives_by_claim,
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

        return SpotifyLibraryReconciliationResult(
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


def reconcile_musicbrainz_releases(  # noqa: PLR0913
    *,
    fetch_release_graph: ReleaseGraphFetcher,
    fetch_candidates_from_recording: ReleaseCandidatesFromRecording,
    fetch_candidates_from_release_set: ReleaseCandidatesFromReleaseSet,
    fetch_candidates_from_artist: ReleaseCandidatesFromArtist,
    unit_of_work_factory: Callable[[], ReconciliationUnitOfWork],
    policy: ReleaseSelectionPolicy | None = None,
    limit: int | None = None,
    engine: ReconciliationEngine | None = None,
) -> MusicBrainzReconciliationResult:
    """Fetch MusicBrainz release graphs and reconcile them into the catalog."""

    active_engine = engine or create_default_reconciliation_engine()

    with unit_of_work_factory() as uow:
        releases = uow.repositories.releases.list()
        candidates = _select_release_candidates(releases, limit=limit)
        if not candidates:
            return MusicBrainzReconciliationResult(
                fetched=0,
                persisted_entities=0,
                persisted_sidecars=0,
                entities=_zero_counters(),
                associations=_zero_counters(),
                links=_zero_counters(),
                manual_review_items=[],
                candidate_releases=0,
                fetched_updates=0,
                applied_releases=0,
                anchor_mismatches=0,
            )

        persisted_entities = 0
        persisted_sidecars = 0
        manual_review_items: list[ManualReviewItem] = []
        entity_counters = _zero_counters()
        association_counters = _zero_counters()
        link_counters = _zero_counters()
        fetched_updates = 0
        applied_releases = 0
        anchor_mismatches = 0

        for release in candidates:
            candidate = resolve_release_candidate(
                release,
                fetch_candidates_from_recording=fetch_candidates_from_recording,
                fetch_candidates_from_release_set=fetch_candidates_from_release_set,
                fetch_candidates_from_artist=fetch_candidates_from_artist,
                policy=policy,
            )
            if candidate is None:
                continue

            graph_release = fetch_release_graph(candidate)
            fetched_updates += 1

            bundle = build_catalog_claim_graph(roots=(graph_release,), source=Provider.MUSICBRAINZ)
            prepared = _prepare_catalog_reconciliation(
                bundle,
                repositories=uow.repositories,
                engine=active_engine,
            )
            anchor_review = _anchor_mismatch_review(
                release,
                prepared=prepared,
            )
            if anchor_review is not None:
                anchor_mismatches += 1
                manual_review_items.append(anchor_review)
                continue

            executed = _apply_prepared_catalog_reconciliation(
                prepared,
                uow=uow,
                engine=active_engine,
            )
            persisted_entities += executed.persistence_result.persisted_entities
            persisted_sidecars += executed.persistence_result.persisted_sidecars
            manual_review_items.extend(executed.apply_result.manual_review_items)
            _bump_counters(entity_counters, executed.apply_result.entities)
            _bump_counters(association_counters, executed.apply_result.associations)
            _bump_counters(link_counters, executed.apply_result.links)
            applied_releases += 1

        return MusicBrainzReconciliationResult(
            fetched=fetched_updates,
            persisted_entities=persisted_entities,
            persisted_sidecars=persisted_sidecars,
            entities=entity_counters,
            associations=association_counters,
            links=link_counters,
            manual_review_items=manual_review_items,
            candidate_releases=len(candidates),
            fetched_updates=fetched_updates,
            applied_releases=applied_releases,
            anchor_mismatches=anchor_mismatches,
        )


def _rebind_play_event(
    event: PlayEvent,
    *,
    bundle: CatalogClaimGraphBundle,
    apply_result: ApplyResult,
    representatives_by_claim: RepresentativesByClaim,
) -> None:
    if event.track is not None:
        materialized_track = bundle.require_materialized_association(
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

    materialized_recording = bundle.require_materialized_entity(
        event.recording,
        apply_result=apply_result,
        representatives_by_claim=representatives_by_claim,
    )
    if not isinstance(materialized_recording, Recording):
        raise TypeError(
            f"Expected materialized Recording, got {type(materialized_recording).__name__}"
        )
    event.user.rebind_play_event(
        event,
        recording=materialized_recording,
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


def _anchor_mismatch_review(
    target_release: Release,
    *,
    prepared: PreparedCatalogReconciliation,
) -> ManualReviewItem | None:
    root_claim_id = _representative_root_claim_id(prepared)
    resolution = prepared.entity_resolutions_by_claim.get(root_claim_id)
    if (
        isinstance(resolution, ResolvedResolution)
        and resolution.target.resolved_id == target_release.resolved_id
    ):
        return None

    candidate_entity_ids: tuple[UUID, ...] = ()
    if isinstance(resolution, ResolvedResolution):
        candidate_entity_ids = (resolution.target.resolved_id,)
    elif isinstance(resolution, AmbiguousResolution | ConflictResolution):
        candidate_entity_ids = tuple(candidate.resolved_id for candidate in resolution.candidates)

    return ManualReviewItem(
        claim_id=root_claim_id,
        subject=ManualReviewSubject.ENTITY,
        kind=EntityType.RELEASE,
        candidate_entity_ids=candidate_entity_ids,
        reason="musicbrainz_anchor_mismatch",
    )


def _representative_root_claim_id(prepared: PreparedCatalogReconciliation) -> UUID:
    if not prepared.bundle.root_claim_ids:
        raise ValueError("MusicBrainz reconciliation bundle has no roots")
    root_claim_id = prepared.bundle.root_claim_ids[0]
    representative = prepared.representatives_by_claim.get(root_claim_id)
    if representative is None:
        return root_claim_id
    return representative.claim_id


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


def _zero_counters() -> ApplyCounters:
    return ApplyCounters()


def _bump_counters(target: ApplyCounters, source: ApplyCounters) -> None:
    target.created += source.created
    target.merged += source.merged
    target.skipped += source.skipped
    target.manual_review += source.manual_review


def _require_catalog_entity(entity: object) -> CatalogEntity:
    if not isinstance(entity, Recording | Release | ReleaseSet | Artist | Label):
        raise TypeError(f"Expected catalog entity, got {type(entity).__name__}")
    return entity
