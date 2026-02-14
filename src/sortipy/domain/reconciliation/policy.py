"""Conflict/merge policy contracts for reconciliation.

Responsibilities of this stage:
- inspect unresolved/ambiguous/conflicting resolutions
- decide concrete apply strategy per claim
- enrich plan instructions with rationale (for audit/debugging)

This stage should be deterministic given:
- claim metadata (source/confidence/event context)
- canonical provenance/history (if supplied by resolver inputs)

TODO:
- handle 1:n cardinality conflicts surfaced after relationship rewiring
  (for example, a child resolving to multiple distinct parents).
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Protocol

from .contracts import (
    AmbiguousEntityResolution,
    ApplyInstruction,
    ApplyStrategy,
    ConflictEntityResolution,
    NewEntityResolution,
    ResolvedEntityResolution,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sortipy.domain.model import EntityType, IdentifiedEntity

    from .claims import EntityClaim
    from .contracts import InstructionsByClaim, ResolutionsByClaim
    from .graph import ClaimGraph


class DecideApplyInstructions(Protocol):
    """Decide executable apply instructions from resolver output."""

    def __call__(
        self,
        resolutions_by_claim: ResolutionsByClaim,
        *,
        graph: ClaimGraph,
    ) -> InstructionsByClaim: ...


def decide_apply_instructions(
    resolutions_by_claim: ResolutionsByClaim,
    *,
    graph: ClaimGraph,
) -> InstructionsByClaim:
    """Convert resolutions to executable apply strategies."""

    instructions: InstructionsByClaim = {}
    resolved_groups: dict[tuple[EntityType, UUID], list[UUID]] = defaultdict(list)
    resolved_targets: dict[UUID, IdentifiedEntity] = {}

    for claim_id, resolution in resolutions_by_claim.items():
        match resolution:
            case NewEntityResolution():
                instructions[claim_id] = ApplyInstruction(
                    strategy=ApplyStrategy.CREATE,
                    reason=resolution.reason or "resolved_as_new",
                )
            case ResolvedEntityResolution():
                resolved_targets[claim_id] = resolution.target
                resolved_groups[
                    (resolution.target.entity_type, resolution.target.resolved_id)
                ].append(claim_id)
            case AmbiguousEntityResolution() | ConflictEntityResolution():
                instructions[claim_id] = ApplyInstruction(
                    strategy=ApplyStrategy.MANUAL_REVIEW,
                    reason=resolution.reason or "manual_review_required",
                )

    for claim_ids in resolved_groups.values():
        winner_id = _best_resolved_claim_id(claim_ids, graph=graph)
        for claim_id in claim_ids:
            target = resolved_targets[claim_id]
            if claim_id == winner_id:
                instructions[claim_id] = ApplyInstruction(
                    strategy=ApplyStrategy.MERGE,
                    target=target,
                    reason="resolved_target_selected",
                )
                continue
            instructions[claim_id] = ApplyInstruction(
                strategy=ApplyStrategy.NOOP,
                target=target,
                reason="duplicate_resolved_target",
            )

    return instructions


def _best_resolved_claim_id(claim_ids: list[UUID], *, graph: ClaimGraph) -> UUID:
    ranked = sorted(claim_ids, key=lambda claim_id: _claim_sort_key(claim_id, graph=graph))
    return ranked[0]


def _claim_sort_key(claim_id: UUID, *, graph: ClaimGraph) -> tuple[float, str]:
    claim = _claim_for_id(claim_id, graph=graph)
    confidence = claim.metadata.confidence if claim.metadata.confidence is not None else -1.0
    # Highest confidence wins; ties break on UUID string for determinism.
    return (-confidence, str(claim_id))


def _claim_for_id(claim_id: UUID, *, graph: ClaimGraph) -> EntityClaim:
    claim = graph.claim_for(claim_id)
    if claim is None:
        msg = f"Resolution references unknown claim {claim_id}"
        raise ValueError(msg)
    return claim
