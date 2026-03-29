"""Application service for release-update reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from logging import getLogger
from typing import TYPE_CHECKING

from sortipy.adapters.musicbrainz.candidates import resolve_release_candidate
from sortipy.adapters.musicbrainz.client import MusicBrainzAPIError
from sortipy.domain.model import EntityType, ExternalNamespace, Provider
from sortipy.domain.reconciliation import (
    AmbiguousResolution,
    ApplyCounters,
    ConflictResolution,
    ManualReviewItem,
    ManualReviewSubject,
    ReconciliationEngine,
    ResolvedResolution,
)

from .claim_graphs import build_catalog_claim_graph
from .ingest import IngestRunResult

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from uuid import UUID

    from sortipy.adapters.musicbrainz.candidates import (
        MusicBrainzReleaseCandidatesFromArtist,
        MusicBrainzReleaseCandidatesFromRecording,
        MusicBrainzReleaseCandidatesFromReleaseSet,
        MusicBrainzReleaseGraphFetcher,
        MusicBrainzReleaseGraphFetchResult,
        MusicBrainzReleaseSelectionPolicy,
    )
    from sortipy.domain.model import Mbid, Release
    from sortipy.domain.reconciliation import PreparedReconciliation
    from sortipy.domain.reconciliation.persist import ReconciliationUnitOfWork


log = getLogger(__name__)


@dataclass(slots=True)
class ReleaseUpdateResult(IngestRunResult):
    candidate_releases: int
    fetched_updates: int
    applied_releases: int
    anchor_mismatches: int


def reconcile_release_updates(  # noqa: PLR0913
    *,
    fetch_release_graph: MusicBrainzReleaseGraphFetcher,
    fetch_candidates_from_recording: MusicBrainzReleaseCandidatesFromRecording,
    fetch_candidates_from_release_set: MusicBrainzReleaseCandidatesFromReleaseSet,
    fetch_candidates_from_artist: MusicBrainzReleaseCandidatesFromArtist,
    unit_of_work_factory: Callable[[], ReconciliationUnitOfWork],
    policy: MusicBrainzReleaseSelectionPolicy | None = None,
    limit: int | None = None,
    source: Provider = Provider.MUSICBRAINZ,
    engine: ReconciliationEngine | None = None,
) -> ReleaseUpdateResult:
    """Fetch release graphs and reconcile them into the catalog."""

    active_engine = engine or ReconciliationEngine.default()

    with unit_of_work_factory() as uow:
        releases = uow.repositories.releases.list()
        candidates = _select_release_candidates(releases, limit=limit)
        if not candidates:
            return ReleaseUpdateResult(
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
                log.info(
                    f"Skipping MusicBrainz reconciliation for release {release.title} "
                    f"({release.id}): no candidate found"
                )
                continue

            try:
                fetch_result = fetch_release_graph(candidate)
            except MusicBrainzAPIError as exc:
                log.warning(
                    "MusicBrainz fetch failed for release %s (%s): candidate_mbid=%s error=%s",
                    release.title,
                    release.id,
                    candidate.mbid,
                    exc,
                )
                continue
            fetched_updates += 1
            redirect_restore = _apply_release_redirect_if_needed(
                release,
                fetch_result=fetch_result,
                uow=uow,
            )
            if isinstance(redirect_restore, ManualReviewItem):
                anchor_mismatches += 1
                manual_review_items.append(redirect_restore)
                log.warning(
                    f"MusicBrainz redirect collision for release {release.title} "
                    f"({release.id}): requested_mbid={candidate.mbid} "
                    f"fetched_mbid={fetch_result.resolved_mbid} "
                    f"candidate_entity_ids={_format_uuid_tuple(redirect_restore.candidate_entity_ids)}"
                )
                continue

            graph_result = build_catalog_claim_graph(roots=(fetch_result.release,), source=source)
            prepared = active_engine.prepare(
                graph_result.graph,
                repositories=uow.repositories,
            )
            anchor_review = _anchor_mismatch_review(release, prepared=prepared)
            if anchor_review is not None:
                _restore_release_redirect_if_needed(release, restore=redirect_restore)
                anchor_mismatches += 1
                manual_review_items.append(anchor_review)
                log.warning(
                    f"MusicBrainz anchor mismatch for release {release.title} "
                    f"({release.id}): requested_mbid={candidate.mbid} "
                    f"fetched_mbid={fetch_result.resolved_mbid or '-'} "
                    f"candidate_entity_ids={_format_uuid_tuple(anchor_review.candidate_entity_ids)}"
                )
                continue

            if fetch_result.redirected:
                uow.repositories.external_id_redirects.save_redirect(
                    ExternalNamespace.MUSICBRAINZ_RELEASE,
                    fetch_result.requested_mbid,
                    fetch_result.resolved_mbid,
                    provider=Provider.MUSICBRAINZ,
                )

            executed = active_engine.execute(prepared, uow=uow)
            persisted_entities += executed.persistence_result.persisted_entities
            persisted_sidecars += executed.persistence_result.persisted_sidecars
            manual_review_items.extend(executed.apply_result.manual_review_items)
            _bump_counters(entity_counters, executed.apply_result.entities)
            _bump_counters(association_counters, executed.apply_result.associations)
            _bump_counters(link_counters, executed.apply_result.links)
            applied_releases += 1

        return ReleaseUpdateResult(
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


def _anchor_mismatch_review(
    target_release: Release,
    *,
    prepared: PreparedReconciliation,
) -> ManualReviewItem | None:
    if not prepared.deduplicated_graph.roots:
        raise ValueError("Release update graph has no roots")
    root_claim_id = prepared.deduplicated_graph.roots[0].claim_id
    representative = prepared.representatives_by_claim.get(root_claim_id)
    if representative is not None:
        root_claim_id = representative.claim_id
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


def _select_release_candidates(
    releases: Iterable[Release],
    *,
    limit: int | None = None,
) -> list[Release]:
    candidates: list[Release] = []
    for release in releases:
        if _has_source(release, Provider.MUSICBRAINZ):
            continue
        candidates.append(release)
        if limit is not None and len(candidates) >= limit:
            break
    return candidates


def _has_source(release: Release, source: Provider) -> bool:
    provenance = release.provenance
    if provenance is None:
        return False
    return source in provenance.sources


def _zero_counters() -> ApplyCounters:
    return ApplyCounters()


def _bump_counters(target: ApplyCounters, source: ApplyCounters) -> None:
    target.created += source.created
    target.merged += source.merged
    target.skipped += source.skipped
    target.manual_review += source.manual_review


def _apply_release_redirect_if_needed(
    target_release: Release,
    *,
    fetch_result: MusicBrainzReleaseGraphFetchResult,
    uow: ReconciliationUnitOfWork,
) -> ManualReviewItem | _ReleaseRedirectRestore | None:
    if not fetch_result.redirected:
        return None
    existing = uow.repositories.releases.get_by_external_id(
        ExternalNamespace.MUSICBRAINZ_RELEASE,
        fetch_result.resolved_mbid,
    )
    if existing is not None and existing.resolved_id != target_release.resolved_id:
        return ManualReviewItem(
            claim_id=fetch_result.release.id,
            subject=ManualReviewSubject.ENTITY,
            kind=EntityType.RELEASE,
            candidate_entity_ids=(existing.resolved_id,),
            reason="musicbrainz_redirect_collision",
        )
    current_entry = target_release.external_ids_by_namespace.get(
        ExternalNamespace.MUSICBRAINZ_RELEASE,
    )
    target_release.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RELEASE,
        fetch_result.resolved_mbid,
        provider=Provider.MUSICBRAINZ,
        replace=True,
    )
    return _ReleaseRedirectRestore(
        previous_mbid=current_entry.value if current_entry is not None else None,
        previous_provider=current_entry.provider if current_entry is not None else None,
    )


@dataclass(slots=True)
class _ReleaseRedirectRestore:
    previous_mbid: Mbid | None
    previous_provider: Provider | None


def _restore_release_redirect_if_needed(
    target_release: Release,
    *,
    restore: _ReleaseRedirectRestore | None,
) -> None:
    if restore is None:
        return
    if restore.previous_mbid is None:
        target_release.remove_external_id(ExternalNamespace.MUSICBRAINZ_RELEASE)
    else:
        target_release.add_external_id(
            ExternalNamespace.MUSICBRAINZ_RELEASE,
            restore.previous_mbid,
            provider=restore.previous_provider,
            replace=True,
        )
    target_release.clear_changed_fields()


def _format_uuid_tuple(values: tuple[UUID, ...]) -> str:
    if not values:
        return "-"
    return ",".join(str(value) for value in values)
