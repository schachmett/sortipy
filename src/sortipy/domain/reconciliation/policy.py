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

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .graph import ClaimGraph
    from .plan import ResolutionPlan


class ReconciliationPolicy(Protocol):
    """Refine a resolution plan into executable apply instructions."""

    def refine(self, plan: ResolutionPlan, *, graph: ClaimGraph) -> ResolutionPlan: ...
