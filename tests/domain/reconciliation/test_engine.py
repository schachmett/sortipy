from __future__ import annotations

from typing import TYPE_CHECKING

from sortipy.domain.model import Artist, Provider
from sortipy.domain.reconciliation import ClaimGraph, ClaimMetadata, EntityClaim
from sortipy.domain.reconciliation.apply import ApplyResult
from sortipy.domain.reconciliation.engine import ReconciliationEngine
from sortipy.domain.reconciliation.persist import PersistenceResult

if TYPE_CHECKING:
    from sortipy.domain.reconciliation.contracts import (
        AssociationInstructionsByClaim,
        AssociationResolutionsByClaim,
        EntityInstructionsByClaim,
        EntityResolutionsByClaim,
        KeysByClaim,
        LinkInstructionsByClaim,
        LinkResolutionsByClaim,
        RepresentativesByClaim,
    )


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
        def __call__(self, graph: ClaimGraph) -> KeysByClaim:
            return {claim.claim_id: () for claim in graph.claims}

    class _Deduplicator:
        def __call__(
            self,
            graph: ClaimGraph,
            *,
            keys_by_claim: KeysByClaim,
        ) -> tuple[ClaimGraph, RepresentativesByClaim]:
            return deduplicated_graph, {}

    class _Resolver:
        def __call__(
            self,
            graph: ClaimGraph,
            *,
            keys_by_claim: KeysByClaim,
        ) -> tuple[
            EntityResolutionsByClaim,
            AssociationResolutionsByClaim,
            LinkResolutionsByClaim,
        ]:
            observed["resolver"] = graph
            return {}, {}, {}

    class _Policy:
        def __call__(
            self,
            entity_resolutions_by_claim: EntityResolutionsByClaim,
            association_resolutions_by_claim: AssociationResolutionsByClaim,
            link_resolutions_by_claim: LinkResolutionsByClaim,
            *,
            graph: ClaimGraph,
        ) -> tuple[
            EntityInstructionsByClaim,
            AssociationInstructionsByClaim,
            LinkInstructionsByClaim,
        ]:
            observed["policy"] = graph
            _ = (
                entity_resolutions_by_claim,
                association_resolutions_by_claim,
                link_resolutions_by_claim,
            )
            return {}, {}, {}

    class _Applier:
        def __call__(
            self,
            graph: ClaimGraph,
            *,
            entity_instructions_by_claim: EntityInstructionsByClaim,
            association_instructions_by_claim: AssociationInstructionsByClaim,
            link_instructions_by_claim: LinkInstructionsByClaim,
        ) -> ApplyResult:
            observed["applier"] = graph
            _ = (
                entity_instructions_by_claim,
                association_instructions_by_claim,
                link_instructions_by_claim,
            )
            return ApplyResult()

    class _Persister:
        def __call__(
            self,
            *,
            entity_instructions_by_claim: EntityInstructionsByClaim,
            association_instructions_by_claim: AssociationInstructionsByClaim,
            link_instructions_by_claim: LinkInstructionsByClaim,
            apply_result: ApplyResult,
        ) -> PersistenceResult:
            _ = (
                entity_instructions_by_claim,
                association_instructions_by_claim,
                link_instructions_by_claim,
                apply_result,
            )
            return PersistenceResult(committed=True)

    engine = ReconciliationEngine(
        normalize=_Normalizer(),
        deduplicate=_Deduplicator(),
        resolve=_Resolver(),
        decide=_Policy(),
        apply=_Applier(),
        persist=_Persister(),
    )
    engine.reconcile(original_graph)

    assert observed["resolver"] is deduplicated_graph
    assert observed["policy"] is deduplicated_graph
    assert observed["applier"] is deduplicated_graph
