"""Intra-batch deduplication contracts for claim graphs.

Responsibilities of this stage:
- collapse duplicate claims within one reconciliation run
- emit mapping from dropped claim IDs to surviving representative IDs
- avoid persistence/database lookups

This is analogous to current ``ingest_pipeline.deduplication`` but should
operate on claim nodes and normalization results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from uuid import UUID

    from .graph import ClaimGraph
    from .normalize import NormalizationResult


@dataclass(slots=True)
class DeduplicationResult:
    """Result of intra-batch claim deduplication."""

    graph: ClaimGraph
    representative_by_claim: dict[UUID, UUID] = field(default_factory=dict["UUID", "UUID"])

    def representative_for(self, claim_id: UUID) -> UUID:
        return self.representative_by_claim.get(claim_id, claim_id)


class ClaimDeduplicator(Protocol):
    """Collapse duplicate claims in a graph."""

    def deduplicate(
        self,
        graph: ClaimGraph,
        *,
        normalization: NormalizationResult,
    ) -> DeduplicationResult: ...
