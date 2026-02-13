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
    from sortipy.domain.model import IdentifiedEntity

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
    [EntityClaim, tuple[ClaimKey, ...]], tuple[IdentifiedEntity, ...]
]


def resolve_claim_graph(
    graph: ClaimGraph,
    *,
    keys_by_claim: KeysByClaim,
    find_exact_candidates: FindExactCandidates | None = None,
) -> ResolutionsByClaim:
    """Resolve claim identities using exact-match candidate lookup.

    Matching policy for this first implementation:
    - no candidates -> ``NewEntityResolution``
    - one candidate -> ``ResolvedEntityResolution``
    - multiple candidates -> ``AmbiguousEntityResolution``
    - mismatched candidate entity type -> ``ConflictEntityResolution``
    """

    finder = find_exact_candidates or _no_exact_candidates
    resolutions_by_claim: ResolutionsByClaim = {}
    for claim in graph.claims:
        keys = keys_by_claim.get(claim.claim_id, ())
        candidates = _dedupe_candidates(finder(claim, keys))
        resolution = _resolution_for_claim(claim, candidates=candidates, matched_key=None)
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


def _no_exact_candidates(
    _claim: EntityClaim, _keys: tuple[ClaimKey, ...]
) -> tuple[IdentifiedEntity, ...]:
    return ()
