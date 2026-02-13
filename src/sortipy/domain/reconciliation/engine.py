"""Orchestrator for the reconciliation subsystem.

The engine composes stage interfaces but does not prescribe concrete adapters.
This allows workflows (play-event ingest, library ingest, MB enrichment) to
share one reconciliation core while providing different translators/fetchers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .apply import ApplyResolutionPlan, ApplyResult
    from .deduplicate import DeduplicateClaimGraph
    from .graph import ClaimGraph
    from .normalize import NormalizeClaimGraph
    from .persist import PersistenceResult, PersistReconciliation
    from .policy import RefineResolutionPlan
    from .resolve import ResolveClaimGraph


@dataclass(slots=True)
class ReconciliationEngine:
    """Run full reconciliation from claim graph to persistence."""

    normalize: NormalizeClaimGraph
    deduplicate: DeduplicateClaimGraph
    resolve: ResolveClaimGraph
    refine: RefineResolutionPlan
    apply: ApplyResolutionPlan
    persist: PersistReconciliation

    def reconcile(self, graph: ClaimGraph) -> tuple[ApplyResult, PersistenceResult]:
        """Run all reconciliation stages for ``graph``."""

        keys_by_claim = self.normalize(graph)
        deduplicated_graph, _representatives_by_claim = self.deduplicate(
            graph,
            keys_by_claim=keys_by_claim,
        )
        resolutions_by_claim = self.resolve(
            deduplicated_graph,
            keys_by_claim=keys_by_claim,
        )
        instructions_by_claim = self.refine(
            resolutions_by_claim,
            graph=deduplicated_graph,
        )
        apply_result = self.apply(
            deduplicated_graph,
            instructions_by_claim=instructions_by_claim,
        )
        persistence_result = self.persist(
            instructions_by_claim=instructions_by_claim,
            apply_result=apply_result,
        )
        return apply_result, persistence_result
