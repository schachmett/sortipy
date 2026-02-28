"""Conflict/merge policy contracts for reconciliation."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Protocol

from sortipy.domain.model import (
    RecordingContribution,
    ReleaseSetContribution,
    ReleaseTrack,
)

from .contracts import (
    AmbiguousResolution,
    BlockedResolution,
    ConflictResolution,
    CreateInstruction,
    LinkConflictResolution,
    LinkCreateInstruction,
    LinkManualReviewInstruction,
    LinkNoopInstruction,
    LinkResolvedResolution,
    ManualReviewInstruction,
    MergeInstruction,
    NewResolution,
    NoopInstruction,
    ResolvedResolution,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sortipy.domain.model import (
        AssociationEntity,
        EntityType,
        IdentifiedEntity,
    )

    from .claims import AssociationClaim
    from .contracts import (
        AssociationInstructionsByClaim,
        AssociationResolutionsByClaim,
        EntityInstructionsByClaim,
        EntityResolutionsByClaim,
        LinkInstructionsByClaim,
        LinkResolutionsByClaim,
    )
    from .graph import ClaimGraph


class DecideApplyInstructions(Protocol):
    """Decide executable apply instructions from resolver output."""

    def __call__(
        self,
        entity_resolutions_by_claim: EntityResolutionsByClaim,
        association_resolutions_by_claim: AssociationResolutionsByClaim,
        link_resolutions_by_claim: LinkResolutionsByClaim,
        *,
        graph: ClaimGraph,
    ) -> tuple[
        EntityInstructionsByClaim, AssociationInstructionsByClaim, LinkInstructionsByClaim
    ]: ...


def decide_apply_instructions(
    entity_resolutions_by_claim: EntityResolutionsByClaim,
    association_resolutions_by_claim: AssociationResolutionsByClaim,
    link_resolutions_by_claim: LinkResolutionsByClaim,
    *,
    graph: ClaimGraph,
) -> tuple[EntityInstructionsByClaim, AssociationInstructionsByClaim, LinkInstructionsByClaim]:
    """Convert resolutions to executable apply strategies."""

    entity_instructions_by_claim = _decide_entity_instructions(
        entity_resolutions_by_claim,
        graph=graph,
    )
    association_instructions_by_claim = _decide_association_instructions(
        association_resolutions_by_claim,
        graph=graph,
    )
    link_instructions_by_claim = _decide_link_instructions(
        link_resolutions_by_claim,
    )

    return (
        entity_instructions_by_claim,
        association_instructions_by_claim,
        link_instructions_by_claim,
    )


def _decide_entity_instructions(
    entity_resolutions_by_claim: EntityResolutionsByClaim,
    *,
    graph: ClaimGraph,
) -> EntityInstructionsByClaim:
    entity_instructions_by_claim: EntityInstructionsByClaim = {}
    resolved_groups: dict[tuple[EntityType, UUID], list[UUID]] = defaultdict(list)
    resolved_targets: dict[UUID, IdentifiedEntity] = {}

    for claim_id, resolution in entity_resolutions_by_claim.items():
        match resolution:
            case NewResolution():
                entity_instructions_by_claim[claim_id] = CreateInstruction(
                    reason=resolution.reason or "resolved_as_new",
                )
            case ResolvedResolution():
                resolved_targets[claim_id] = resolution.target
                resolved_groups[
                    (resolution.target.entity_type, resolution.target.resolved_id)
                ].append(claim_id)
            case AmbiguousResolution() | ConflictResolution() as unresolved:
                entity_instructions_by_claim[claim_id] = ManualReviewInstruction(
                    candidate_entity_ids=_candidate_entity_ids(unresolved.candidates),
                    reason=resolution.reason or "manual_review_required",
                )

    for claim_ids in resolved_groups.values():
        winner_id = _best_resolved_claim_id(claim_ids, graph=graph)
        for claim_id in claim_ids:
            target = resolved_targets[claim_id]
            if claim_id == winner_id:
                entity_instructions_by_claim[claim_id] = MergeInstruction(
                    target=target,
                    reason="resolved_target_selected",
                )
                continue
            entity_instructions_by_claim[claim_id] = NoopInstruction(
                target=target,
                reason="duplicate_resolved_target",
            )

    return entity_instructions_by_claim


def _decide_association_instructions(
    association_resolutions_by_claim: AssociationResolutionsByClaim,
    *,
    graph: ClaimGraph,
) -> AssociationInstructionsByClaim:
    association_instructions_by_claim: AssociationInstructionsByClaim = {}
    for claim_id, resolution in association_resolutions_by_claim.items():
        match resolution:
            case NewResolution():
                association_instructions_by_claim[claim_id] = CreateInstruction(
                    reason=resolution.reason or "association_create",
                )
            case ResolvedResolution():
                association_claim = graph.require_association(claim_id)
                if _requires_association_merge(association_claim, resolution=resolution):
                    association_instructions_by_claim[claim_id] = MergeInstruction(
                        target=resolution.target,
                        reason="association_payload_merge",
                    )
                else:
                    association_instructions_by_claim[claim_id] = NoopInstruction(
                        target=resolution.target,
                        reason=resolution.reason or "association_noop",
                    )
            case BlockedResolution() | AmbiguousResolution() | ConflictResolution() as unresolved:
                blocked_by_claim_ids = (
                    unresolved.blocked_by_claim_ids
                    if isinstance(unresolved, BlockedResolution)
                    else ()
                )
                candidate_entity_ids = (
                    _candidate_entity_ids(unresolved.candidates)
                    if isinstance(unresolved, (AmbiguousResolution, ConflictResolution))
                    else ()
                )
                association_instructions_by_claim[claim_id] = ManualReviewInstruction(
                    blocked_by_claim_ids=blocked_by_claim_ids,
                    candidate_entity_ids=candidate_entity_ids,
                    reason=resolution.reason or "association_manual_review_required",
                )
    return association_instructions_by_claim


def _decide_link_instructions(
    link_resolutions_by_claim: LinkResolutionsByClaim,
) -> LinkInstructionsByClaim:
    link_instructions_by_claim: LinkInstructionsByClaim = {}
    for claim_id, resolution in link_resolutions_by_claim.items():
        match resolution:
            case NewResolution():
                link_instructions_by_claim[claim_id] = LinkCreateInstruction(
                    reason=resolution.reason or "link_create",
                )
            case LinkResolvedResolution():
                link_instructions_by_claim[claim_id] = LinkNoopInstruction(
                    reason=resolution.reason or "link_exists",
                )
            case BlockedResolution():
                link_instructions_by_claim[claim_id] = LinkManualReviewInstruction(
                    blocked_by_claim_ids=resolution.blocked_by_claim_ids,
                    reason=resolution.reason or "link_endpoint_blocked",
                )
            case LinkConflictResolution():
                link_instructions_by_claim[claim_id] = LinkManualReviewInstruction(
                    reason=resolution.reason or "link_manual_review_required",
                )
    return link_instructions_by_claim


def _candidate_entity_ids(candidates: tuple[IdentifiedEntity, ...]) -> tuple[UUID, ...]:
    return tuple(dict.fromkeys(candidate.resolved_id for candidate in candidates))


def _requires_association_merge(
    association_claim: AssociationClaim,
    *,
    resolution: ResolvedResolution[AssociationEntity],
) -> bool:
    incoming_payload = association_claim.payload
    existing_payload = resolution.target

    if incoming_payload is None:
        return False
    if type(incoming_payload) is not type(existing_payload):
        msg = (
            "association_payload_type_mismatch:"
            f"{type(incoming_payload).__name__}!={type(existing_payload).__name__}"
        )
        raise TypeError(msg)

    return _association_payload_differs(incoming_payload, existing_payload)


type MergeableAssociationPayload = ReleaseSetContribution | RecordingContribution | ReleaseTrack


def _association_payload_differs[TAssociation: MergeableAssociationPayload](
    incoming: TAssociation,
    existing: TAssociation,
) -> bool:
    match (incoming, existing):
        case (ReleaseSetContribution(), ReleaseSetContribution()):
            return (
                incoming.role != existing.role
                or incoming.credit_order != existing.credit_order
                or incoming.credited_as != existing.credited_as
                or incoming.join_phrase != existing.join_phrase
            )
        case (RecordingContribution(), RecordingContribution()):
            return (
                incoming.role != existing.role
                or incoming.credit_order != existing.credit_order
                or incoming.credited_as != existing.credited_as
                or incoming.join_phrase != existing.join_phrase
            )
        case (ReleaseTrack(), ReleaseTrack()):
            return (
                incoming.disc_number != existing.disc_number
                or incoming.track_number != existing.track_number
                or incoming.title_override != existing.title_override
                or incoming.duration_ms != existing.duration_ms
            )
        case _:
            msg = (
                "unsupported_association_payload_type:"
                f"{type(incoming).__name__}/{type(existing).__name__}"
            )
            raise TypeError(msg)


def _best_resolved_claim_id(claim_ids: list[UUID], *, graph: ClaimGraph) -> UUID:
    ranked = sorted(claim_ids, key=lambda claim_id: _claim_sort_key(claim_id, graph=graph))
    return ranked[0]


def _claim_sort_key(claim_id: UUID, *, graph: ClaimGraph) -> tuple[float, str]:
    claim = graph.require_claim(claim_id)
    confidence = claim.metadata.confidence if claim.metadata.confidence is not None else -1.0
    # Highest confidence wins; ties break on UUID string for determinism.
    return (-confidence, str(claim_id))
