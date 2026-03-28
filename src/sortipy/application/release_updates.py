"""Application service for release-update reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sortipy.adapters.musicbrainz.candidates import (
    resolve_release_candidate,
)
from sortipy.domain.model import EntityType, Provider
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
        MusicBrainzReleaseSelectionPolicy,
    )
    from sortipy.domain.model import Release
    from sortipy.domain.reconciliation import PreparedReconciliation
    from sortipy.domain.reconciliation.persist import ReconciliationUnitOfWork


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
                continue

            graph_release = fetch_release_graph(candidate)
            fetched_updates += 1

            graph_result = build_catalog_claim_graph(roots=(graph_release,), source=source)
            prepared = active_engine.prepare(
                graph_result.graph,
                repositories=uow.repositories,
            )
            anchor_review = _anchor_mismatch_review(release, prepared=prepared)
            if anchor_review is not None:
                anchor_mismatches += 1
                manual_review_items.append(anchor_review)
                continue

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
