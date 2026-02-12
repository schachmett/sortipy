from __future__ import annotations

from sortipy.domain.model import Artist, Provider
from sortipy.domain.reconciliation import ClaimGraph, ClaimMetadata, EntityClaim
from sortipy.domain.reconciliation.apply import ApplyResult
from sortipy.domain.reconciliation.deduplicate import DeduplicationResult
from sortipy.domain.reconciliation.engine import ReconciliationEngine
from sortipy.domain.reconciliation.normalize import NormalizationResult
from sortipy.domain.reconciliation.persist import PersistenceResult
from sortipy.domain.reconciliation.plan import ResolutionPlan


def test_engine_uses_deduplicated_graph_after_deduplication() -> None:
    original_graph = ClaimGraph()
    original_graph.add(
        EntityClaim(
            entity=Artist(name="Original"),
            metadata=ClaimMetadata(source=Provider.SPOTIFY),
        )
    )

    deduplicated_graph = ClaimGraph()
    deduplicated_graph.add(
        EntityClaim(
            entity=Artist(name="Deduped"),
            metadata=ClaimMetadata(source=Provider.SPOTIFY),
        )
    )

    observed: dict[str, ClaimGraph] = {}

    class _Normalizer:
        def normalize(self, graph: ClaimGraph) -> NormalizationResult:
            return NormalizationResult(keys_by_claim={claim.claim_id: () for claim in graph.claims})

    class _Deduplicator:
        def deduplicate(
            self, graph: ClaimGraph, *, normalization: NormalizationResult
        ) -> DeduplicationResult:
            return DeduplicationResult(graph=deduplicated_graph)

    class _Resolver:
        def resolve(
            self,
            graph: ClaimGraph,
            *,
            deduplication: DeduplicationResult,
        ) -> ResolutionPlan:
            observed["resolver"] = graph
            return ResolutionPlan()

    class _Policy:
        def refine(self, plan: ResolutionPlan, *, graph: ClaimGraph) -> ResolutionPlan:
            observed["policy"] = graph
            return plan

    class _Applier:
        def apply(self, graph: ClaimGraph, *, plan: ResolutionPlan) -> ApplyResult:
            observed["applier"] = graph
            return ApplyResult()

    class _Persister:
        def persist(self, *, plan: ResolutionPlan, apply_result: ApplyResult) -> PersistenceResult:
            return PersistenceResult(committed=True)

    engine = ReconciliationEngine(
        normalizer=_Normalizer(),
        deduplicator=_Deduplicator(),
        resolver=_Resolver(),
        policy=_Policy(),
        applier=_Applier(),
        persister=_Persister(),
    )
    engine.reconcile(original_graph)

    assert observed["resolver"] is deduplicated_graph
    assert observed["policy"] is deduplicated_graph
    assert observed["applier"] is deduplicated_graph
