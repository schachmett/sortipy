"""Canonical identity resolution contracts.

Responsibilities of this stage:
- resolve claim representatives against canonical entities from repositories
- classify each claim as NEW/RESOLVED/AMBIGUOUS/CONFLICT
- produce ``ResolutionsByClaim`` without mutating persistence state

TODO:
- consume richer key evidence directly from normalization output so resolver
  implementations can combine exact lookup and fuzzy matching without
  recomputing normalization.

Out of scope for this stage:
- conflict policy decisions
- domain mutation
- commit/flush
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from .contracts import (
    AmbiguousEntityResolution,
    ConflictEntityResolution,
    MatchKind,
    NewEntityResolution,
    ResolvedEntityResolution,
)

if TYPE_CHECKING:
    from sortipy.domain.model import IdentifiedEntity, Namespace

    from .claims import EntityClaim
    from .contracts import ClaimKey, EntityResolution, KeysByClaim, ResolutionsByClaim
    from .graph import ClaimGraph


class ResolveClaimGraph(Protocol):
    """Resolve claims against canonical catalog state."""

    def __call__(
        self,
        graph: ClaimGraph,
        *,
        keys_by_claim: KeysByClaim,
    ) -> ResolutionsByClaim: ...


type FindExactCandidates = Callable[
    [EntityClaim, tuple[ClaimKey, ...]],
    tuple[tuple[IdentifiedEntity, ...], ClaimKey | None],
]
type FindByExternalId = Callable[[EntityClaim, Namespace, str], tuple[IdentifiedEntity, ...]]
type FindByNormalizedKey = Callable[[EntityClaim, ClaimKey], tuple[IdentifiedEntity, ...]]


def resolve_claim_graph(
    graph: ClaimGraph,
    *,
    keys_by_claim: KeysByClaim,
    find_exact_candidates: FindExactCandidates | None = None,
    find_by_external_id: FindByExternalId | None = None,
    find_by_normalized_key: FindByNormalizedKey | None = None,
) -> ResolutionsByClaim:
    """Resolve claim identities using exact-match candidate lookup.

    Matching policy for this first implementation:
    - no candidates -> ``NewEntityResolution``
    - one candidate -> ``ResolvedEntityResolution``
    - multiple candidates -> ``AmbiguousEntityResolution``
    - mismatched candidate entity type -> ``ConflictEntityResolution``
    """

    finder = find_exact_candidates or _default_exact_candidate_finder(
        find_by_external_id=find_by_external_id,
        find_by_normalized_key=find_by_normalized_key,
    )
    resolutions_by_claim: ResolutionsByClaim = {}
    for claim in graph.claims:
        keys = keys_by_claim.get(claim.claim_id, ())
        candidates, matched_key = finder(claim, keys)
        resolution = _resolution_for_claim(
            claim,
            candidates=_dedupe_candidates(candidates),
            matched_key=matched_key,
        )
        resolutions_by_claim[claim.claim_id] = resolution
    return resolutions_by_claim


def _resolution_for_claim(
    claim: EntityClaim,
    *,
    candidates: tuple[IdentifiedEntity, ...],
    matched_key: ClaimKey | None,
) -> EntityResolution:
    if any(candidate.entity_type is not claim.entity_type for candidate in candidates):
        return ConflictEntityResolution(
            candidates=candidates,
            matched_key=matched_key,
            match_kind=MatchKind.EXACT,
            reason="candidate_type_mismatch",
        )

    if not candidates:
        return NewEntityResolution(reason="no_exact_match")

    if len(candidates) == 1:
        return ResolvedEntityResolution(
            target=candidates[0],
            matched_key=matched_key,
            match_kind=MatchKind.EXACT,
            reason="exact_match",
        )

    return AmbiguousEntityResolution(
        candidates=candidates,
        matched_key=matched_key,
        match_kind=MatchKind.EXACT,
        reason="multiple_exact_matches",
    )


def _dedupe_candidates(
    candidates: tuple[IdentifiedEntity, ...],
) -> tuple[IdentifiedEntity, ...]:
    seen: set[tuple[object, object]] = set()
    deduped: list[IdentifiedEntity] = []
    for candidate in candidates:
        key = (candidate.entity_type, candidate.resolved_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return tuple(deduped)


def _default_exact_candidate_finder(
    *,
    find_by_external_id: FindByExternalId | None,
    find_by_normalized_key: FindByNormalizedKey | None,
) -> Callable[
    [EntityClaim, tuple[ClaimKey, ...]],
    tuple[tuple[IdentifiedEntity, ...], ClaimKey | None],
]:
    def find_exact_candidates(
        claim: EntityClaim,
        keys: tuple[ClaimKey, ...],
    ) -> tuple[tuple[IdentifiedEntity, ...], ClaimKey | None]:
        external_lookup = _match_from_external_ids(claim, find_by_external_id=find_by_external_id)
        if external_lookup is not None:
            return external_lookup

        key_lookup = _match_from_keys(
            claim,
            keys,
            find_by_normalized_key=find_by_normalized_key,
        )
        if key_lookup is not None:
            return key_lookup

        return (), None

    return find_exact_candidates


def _match_from_external_ids(
    claim: EntityClaim,
    *,
    find_by_external_id: FindByExternalId | None,
) -> tuple[tuple[IdentifiedEntity, ...], ClaimKey] | None:
    if find_by_external_id is None:
        return None
    if not hasattr(claim.entity, "external_ids"):
        return None

    external_ids = getattr(claim.entity, "external_ids", ())
    for external_id in external_ids:
        candidates = find_by_external_id(claim, external_id.namespace, external_id.value)
        if candidates:
            return candidates, ("external_id", external_id.namespace, external_id.value)
    return None


def _match_from_keys(
    claim: EntityClaim,
    keys: tuple[ClaimKey, ...],
    *,
    find_by_normalized_key: FindByNormalizedKey | None,
) -> tuple[tuple[IdentifiedEntity, ...], ClaimKey] | None:
    if find_by_normalized_key is None:
        return None

    all_candidates: list[IdentifiedEntity] = []
    matched_key: ClaimKey | None = None
    for key in keys:
        candidates = find_by_normalized_key(claim, key)
        if not candidates:
            continue
        if matched_key is None:
            matched_key = key
        all_candidates.extend(candidates)
    if not all_candidates or matched_key is None:
        return None
    return tuple(all_candidates), matched_key
