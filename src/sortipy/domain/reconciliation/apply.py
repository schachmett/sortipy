"""Domain mutation contracts for reconciliation instructions.

Responsibilities of this stage:
- execute policy instructions via domain commands
- mutate canonical entities in memory
- avoid direct commit/transaction control

The implementation should keep all ORM-specific behavior out of this module.
Any session re-attachment/hydration concerns belong to persistence adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from .contracts import ApplyStrategy

if TYPE_CHECKING:
    from .claims import EntityClaim
    from .contracts import ApplyInstruction, InstructionsByClaim
    from .graph import ClaimGraph


@dataclass(slots=True)
class ApplyResult:
    """Summary of in-memory mutations performed by the applier."""

    applied: int = 0
    created: int = 0
    merged: int = 0
    skipped: int = 0
    manual_review: int = 0


class ApplyResolutionPlan(Protocol):
    """Apply policy instructions to canonical domain entities."""

    def __call__(
        self,
        graph: ClaimGraph,
        *,
        instructions_by_claim: InstructionsByClaim,
    ) -> ApplyResult: ...


def apply_resolution_plan(
    graph: ClaimGraph,
    *,
    instructions_by_claim: InstructionsByClaim,
) -> ApplyResult:
    """Apply policy instructions to claim entities in ``graph``.

    This first implementation intentionally keeps mutation semantics narrow:
    - ``CREATE``: mark claim as to-be-created (no in-memory mutation needed)
    - ``MERGE``: point claim entity to canonical target via ``point_to_canonical``
    - ``NOOP``: keep claim unchanged
    - ``MANUAL_REVIEW``: keep claim unchanged

    TODO:
    - apply field-level merge semantics once policy can decide per-attribute precedence
    - handle relationship-claim application after relationship conflict policies exist
    """

    result = ApplyResult()
    for claim_id, instruction in instructions_by_claim.items():
        claim = _claim_for_id(graph, claim_id)
        _apply_instruction(claim, instruction, result=result)
    return result


def _apply_instruction(
    claim: EntityClaim,
    instruction: ApplyInstruction,
    *,
    result: ApplyResult,
) -> None:
    match instruction.strategy:
        case ApplyStrategy.CREATE:
            result.created += 1
        case ApplyStrategy.MERGE:
            _apply_merge(claim, instruction)
            result.merged += 1
        case ApplyStrategy.NOOP:
            result.skipped += 1
        case ApplyStrategy.MANUAL_REVIEW:
            result.manual_review += 1
    result.applied += 1


def _apply_merge(claim: EntityClaim, instruction: ApplyInstruction) -> None:
    target = instruction.target
    if target is None:
        msg = f"MERGE instruction for claim {claim.claim_id} is missing target"
        raise ValueError(msg)

    point_to_canonical = getattr(claim.entity, "point_to_canonical", None)
    if not callable(point_to_canonical):
        msg = (
            f"Claim {claim.claim_id} entity type {claim.entity_type} "
            "does not support canonical merge"
        )
        raise TypeError(msg)

    point_to_canonical(target)


def _claim_for_id(graph: ClaimGraph, claim_id: object) -> EntityClaim:
    claim = graph.claim_for(claim_id)  # type: ignore[arg-type]
    if claim is None:
        msg = f"Apply instruction references unknown claim {claim_id}"
        raise ValueError(msg)
    return claim
