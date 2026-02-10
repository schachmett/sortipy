"""Orchestrator for the reconciliation subsystem.

The engine composes stage interfaces but does not prescribe concrete adapters.
This allows workflows (play-event ingest, library ingest, MB enrichment) to
share one reconciliation core while providing different translators/fetchers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .apply import ApplyResult, PlanApplier
    from .deduplicate import ClaimDeduplicator
    from .graph import ClaimGraph
    from .normalize import ClaimNormalizer
    from .persist import PersistenceResult, PlanPersister
    from .policy import ReconciliationPolicy
    from .resolve import IdentityResolver


@dataclass(slots=True)
class ReconciliationEngine:
    """Run full reconciliation from claim graph to persistence."""

    normalizer: ClaimNormalizer
    deduplicator: ClaimDeduplicator
    resolver: IdentityResolver
    policy: ReconciliationPolicy
    applier: PlanApplier
    persister: PlanPersister

    def reconcile(self, graph: ClaimGraph) -> tuple[ApplyResult, PersistenceResult]:
        """Run all reconciliation stages for ``graph``."""

        normalization = self.normalizer.normalize(graph)
        deduplication = self.deduplicator.deduplicate(graph, normalization=normalization)
        plan = self.resolver.resolve(graph, deduplication=deduplication)
        refined_plan = self.policy.refine(plan, graph=graph)
        apply_result = self.applier.apply(graph, plan=refined_plan)
        persistence_result = self.persister.persist(
            plan=refined_plan,
            apply_result=apply_result,
        )
        return apply_result, persistence_result
