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

        normalization = self.normalize(graph)
        deduplication = self.deduplicate(graph, normalization=normalization)
        deduplicated_graph = deduplication.graph
        plan = self.resolve(deduplicated_graph, deduplication=deduplication)
        refined_plan = self.refine(plan, graph=deduplicated_graph)
        apply_result = self.apply(deduplicated_graph, plan=refined_plan)
        persistence_result = self.persist(
            plan=refined_plan,
            apply_result=apply_result,
        )
        return apply_result, persistence_result
