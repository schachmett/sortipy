from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sortipy.domain.model import Artist, Label, Provider, ReleaseSet
from sortipy.domain.reconciliation import (
    AssociationClaim,
    AssociationKind,
    ClaimGraph,
    ClaimMetadata,
    EntityClaim,
    LinkClaim,
    LinkKind,
)
from sortipy.domain.reconciliation.contracts import (
    AmbiguousResolution,
    BlockedResolution,
    ConflictResolution,
    CreateInstruction,
    LinkCreateInstruction,
    LinkManualReviewInstruction,
    LinkNoopInstruction,
    LinkResolvedResolution,
    ManualReviewInstruction,
    MatchKind,
    MergeInstruction,
    NewResolution,
    NoopInstruction,
    ResolvedResolution,
)
from sortipy.domain.reconciliation.policy import decide_apply_instructions

if TYPE_CHECKING:
    from sortipy.domain.reconciliation.contracts import (
        AssociationResolutionsByClaim,
        EntityResolutionsByClaim,
        LinkResolutionsByClaim,
    )


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
    entity_resolutions: EntityResolutionsByClaim = {
        new_claim.claim_id: NewResolution(reason="no_exact_match"),
        resolved_claim.claim_id: ResolvedResolution(
            target=target,
            match_kind=MatchKind.EXACT,
            reason="exact_match",
        ),
        ambiguous_claim.claim_id: AmbiguousResolution(
            candidates=(Artist(name="A"), Artist(name="B")),
            reason="multiple_exact_matches",
        ),
        conflict_claim.claim_id: ConflictResolution(
            candidates=(Artist(name="X"), Artist(name="Y")),
            reason="candidate_type_mismatch",
        ),
    }

    entity_instructions, association_instructions, link_instructions = decide_apply_instructions(
        entity_resolutions,
        association_resolutions_by_claim={},
        link_resolutions_by_claim={},
        graph=graph,
    )

    assert isinstance(entity_instructions[new_claim.claim_id], CreateInstruction)
    assert isinstance(entity_instructions[resolved_claim.claim_id], MergeInstruction)
    ambiguous_instruction = entity_instructions[ambiguous_claim.claim_id]
    assert isinstance(ambiguous_instruction, ManualReviewInstruction)
    assert len(ambiguous_instruction.candidate_entity_ids) == 2
    conflict_instruction = entity_instructions[conflict_claim.claim_id]
    assert isinstance(conflict_instruction, ManualReviewInstruction)
    assert len(conflict_instruction.candidate_entity_ids) == 2
    assert association_instructions == {}
    assert link_instructions == {}


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
    entity_resolutions: EntityResolutionsByClaim = {
        low_confidence_claim.claim_id: ResolvedResolution(
            target=target,
            match_kind=MatchKind.EXACT,
        ),
        high_confidence_claim.claim_id: ResolvedResolution(
            target=target,
            match_kind=MatchKind.EXACT,
        ),
    }

    entity_instructions, _association_instructions, _link_instructions = decide_apply_instructions(
        entity_resolutions,
        association_resolutions_by_claim={},
        link_resolutions_by_claim={},
        graph=graph,
    )

    assert isinstance(entity_instructions[high_confidence_claim.claim_id], MergeInstruction)
    low_instruction = entity_instructions[low_confidence_claim.claim_id]
    assert isinstance(low_instruction, NoopInstruction)
    assert low_instruction.target == target


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
    entity_resolutions: EntityResolutionsByClaim = {
        first_claim.claim_id: ResolvedResolution(
            target=target,
            match_kind=MatchKind.EXACT,
        ),
        second_claim.claim_id: ResolvedResolution(
            target=target,
            match_kind=MatchKind.EXACT,
        ),
    }

    entity_instructions, _association_instructions, _link_instructions = decide_apply_instructions(
        entity_resolutions,
        association_resolutions_by_claim={},
        link_resolutions_by_claim={},
        graph=graph,
    )

    assert isinstance(entity_instructions[first_claim.claim_id], MergeInstruction)
    assert isinstance(entity_instructions[second_claim.claim_id], NoopInstruction)


def test_decide_apply_instructions_maps_association_and_link_resolutions() -> None:
    source_claim = EntityClaim(
        entity=ReleaseSet(title="Source"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    target_artist_claim = EntityClaim(
        entity=Artist(name="Target"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    target_label_claim = EntityClaim(
        entity=Label(name="Label"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )

    association_claim = AssociationClaim(
        source_claim_id=source_claim.claim_id,
        target_claim_id=target_artist_claim.claim_id,
        kind=AssociationKind.RELEASE_SET_CONTRIBUTION,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    link_claim = LinkClaim(
        source_claim_id=source_claim.claim_id,
        target_claim_id=target_label_claim.claim_id,
        kind=LinkKind.RELEASE_LABEL,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )

    graph = ClaimGraph()
    graph.add(source_claim)
    graph.add(target_artist_claim)
    graph.add(target_label_claim)
    graph.add_relationship(association_claim)
    graph.add_relationship(link_claim)

    association_resolutions: AssociationResolutionsByClaim = {
        association_claim.claim_id: NewResolution(),
    }
    link_resolutions: LinkResolutionsByClaim = {
        link_claim.claim_id: BlockedResolution(
            blocked_by_claim_ids=(source_claim.claim_id,),
        ),
    }

    _entity_instructions, association_instructions, link_instructions = decide_apply_instructions(
        entity_resolutions_by_claim={},
        association_resolutions_by_claim=association_resolutions,
        link_resolutions_by_claim=link_resolutions,
        graph=graph,
    )

    assert isinstance(association_instructions[association_claim.claim_id], CreateInstruction)
    assert isinstance(link_instructions[link_claim.claim_id], LinkManualReviewInstruction)


def test_decide_apply_instructions_maps_resolved_link_to_noop() -> None:
    source_release_set = ReleaseSet(title="Source")
    source_release = source_release_set.create_release(title="Source")
    target_label = Label(name="Target")

    source_claim = EntityClaim(
        entity=source_release,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    target_claim = EntityClaim(
        entity=target_label,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    link_claim = LinkClaim(
        source_claim_id=source_claim.claim_id,
        target_claim_id=target_claim.claim_id,
        kind=LinkKind.RELEASE_LABEL,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )

    graph = ClaimGraph()
    graph.add(source_claim)
    graph.add(target_claim)
    graph.add_relationship(link_claim)

    _entity_instructions, _association_instructions, link_instructions = decide_apply_instructions(
        entity_resolutions_by_claim={},
        association_resolutions_by_claim={},
        link_resolutions_by_claim={link_claim.claim_id: LinkResolvedResolution()},
        graph=graph,
    )
    assert isinstance(link_instructions[link_claim.claim_id], LinkNoopInstruction)


def test_decide_apply_instructions_maps_new_link_to_create() -> None:
    source_claim = EntityClaim(
        entity=ReleaseSet(title="Source"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    target_claim = EntityClaim(
        entity=Label(name="Target"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    link_claim = LinkClaim(
        source_claim_id=source_claim.claim_id,
        target_claim_id=target_claim.claim_id,
        kind=LinkKind.RELEASE_LABEL,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )

    graph = ClaimGraph()
    graph.add(source_claim)
    graph.add(target_claim)
    graph.add_relationship(link_claim)

    _entity_instructions, _association_instructions, link_instructions = decide_apply_instructions(
        entity_resolutions_by_claim={},
        association_resolutions_by_claim={},
        link_resolutions_by_claim={link_claim.claim_id: NewResolution()},
        graph=graph,
    )
    assert isinstance(link_instructions[link_claim.claim_id], LinkCreateInstruction)
