"""Canonical identity resolution contracts.

Responsibilities of this stage:
- resolve claim representatives against canonical entities from repositories
- classify each claim as NEW/RESOLVED/AMBIGUOUS/CONFLICT
- produce a ``ResolutionPlan`` without mutating persistence state

TODO:
- consume normalization artifacts directly (or through deduplication result)
  so resolver implementations can combine exact lookup and fuzzy matching
  without recomputing normalization.

Out of scope for this stage:
- conflict policy decisions
- domain mutation
- commit/flush
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .deduplicate import DeduplicationResult
    from .graph import ClaimGraph
    from .plan import ResolutionPlan


class IdentityResolver(Protocol):
    """Resolve claims against canonical catalog state."""

    def resolve(
        self,
        graph: ClaimGraph,
        *,
        deduplication: DeduplicationResult,
    ) -> ResolutionPlan: ...
