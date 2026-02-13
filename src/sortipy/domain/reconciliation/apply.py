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

if TYPE_CHECKING:
    from .contracts import InstructionsByClaim
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
