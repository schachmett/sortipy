from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sortipy.domain.model import Artist, Provider
from sortipy.domain.reconciliation import ClaimGraph, ClaimMetadata, EntityClaim
from sortipy.domain.reconciliation.contracts import (
    AmbiguousEntityResolution,
    ApplyStrategy,
    ConflictEntityResolution,
    MatchKind,
    NewEntityResolution,
    ResolvedEntityResolution,
)
from sortipy.domain.reconciliation.policy import decide_apply_instructions

if TYPE_CHECKING:
    from sortipy.domain.reconciliation.contracts import ResolutionsByClaim


def test_decide_apply_instructions_maps_resolution_statuses_to_strategies() -> None:
    new_claim = EntityClaim(
        entity=Artist(name="New Artist"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    resolved_claim = EntityClaim(
        entity=Artist(name="Resolved Artist"),
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    ambiguous_claim = EntityClaim(
        entity=Artist(name="Ambiguous Artist"),
        metadata=ClaimMetadata(source=Provider.LASTFM),
    )
    conflict_claim = EntityClaim(
        entity=Artist(name="Conflict Artist"),
        metadata=ClaimMetadata(source=Provider.LASTFM),
    )

    graph = ClaimGraph()
    graph.add(new_claim)
    graph.add(resolved_claim)
    graph.add(ambiguous_claim)
    graph.add(conflict_claim)

    target = Artist(name="Canonical Artist")
    resolutions: ResolutionsByClaim = {
        new_claim.claim_id: NewEntityResolution(reason="no_exact_match"),
        resolved_claim.claim_id: ResolvedEntityResolution(
            target=target,
            match_kind=MatchKind.EXACT,
            reason="exact_match",
        ),
        ambiguous_claim.claim_id: AmbiguousEntityResolution(
            candidates=(Artist(name="A"), Artist(name="B")),
            reason="multiple_exact_matches",
        ),
        conflict_claim.claim_id: ConflictEntityResolution(
            candidates=(Artist(name="X"), Artist(name="Y")),
            reason="candidate_type_mismatch",
        ),
    }

    instructions = decide_apply_instructions(resolutions, graph=graph)

    assert instructions[new_claim.claim_id].strategy is ApplyStrategy.CREATE
    assert instructions[resolved_claim.claim_id].strategy is ApplyStrategy.MERGE
    assert instructions[ambiguous_claim.claim_id].strategy is ApplyStrategy.MANUAL_REVIEW
    assert instructions[conflict_claim.claim_id].strategy is ApplyStrategy.MANUAL_REVIEW


def test_decide_apply_instructions_coalesces_resolved_claims_with_same_target() -> None:
    low_confidence_claim = EntityClaim(
        entity=Artist(name="Claim A"),
        metadata=ClaimMetadata(source=Provider.LASTFM, confidence=0.2),
    )
    high_confidence_claim = EntityClaim(
        entity=Artist(name="Claim B"),
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ, confidence=0.95),
    )

    graph = ClaimGraph()
    graph.add(low_confidence_claim)
    graph.add(high_confidence_claim)

    target = Artist(name="Canonical Target")
    resolutions: ResolutionsByClaim = {
        low_confidence_claim.claim_id: ResolvedEntityResolution(
            target=target,
            match_kind=MatchKind.EXACT,
        ),
        high_confidence_claim.claim_id: ResolvedEntityResolution(
            target=target,
            match_kind=MatchKind.EXACT,
        ),
    }

    instructions = decide_apply_instructions(resolutions, graph=graph)

    assert instructions[high_confidence_claim.claim_id].strategy is ApplyStrategy.MERGE
    assert instructions[low_confidence_claim.claim_id].strategy is ApplyStrategy.NOOP
    assert instructions[low_confidence_claim.claim_id].target == target


def test_decide_apply_instructions_tie_breaks_on_claim_id() -> None:
    first_claim = EntityClaim(
        claim_id=UUID("00000000-0000-0000-0000-000000000001"),
        entity=Artist(name="Claim One"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    second_claim = EntityClaim(
        claim_id=UUID("00000000-0000-0000-0000-000000000002"),
        entity=Artist(name="Claim Two"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )

    graph = ClaimGraph()
    graph.add(first_claim)
    graph.add(second_claim)

    target = Artist(name="Canonical")
    resolutions: ResolutionsByClaim = {
        first_claim.claim_id: ResolvedEntityResolution(
            target=target,
            match_kind=MatchKind.EXACT,
        ),
        second_claim.claim_id: ResolvedEntityResolution(
            target=target,
            match_kind=MatchKind.EXACT,
        ),
    }

    instructions = decide_apply_instructions(resolutions, graph=graph)

    assert instructions[first_claim.claim_id].strategy is ApplyStrategy.MERGE
    assert instructions[second_claim.claim_id].strategy is ApplyStrategy.NOOP
