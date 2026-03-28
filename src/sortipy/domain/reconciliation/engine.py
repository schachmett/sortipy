"""Orchestrator for the reconciliation subsystem."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sortipy.domain.model import Release

from .apply import apply_reconciliation_instructions
from .deduplicate import deduplicate_claim_graph
from .normalize import normalize_claim_graph
from .persist import persist_reconciliation
from .policy import decide_apply_instructions
from .resolve import resolve_claim_graph

if TYPE_CHECKING:
    from .apply import ApplyReconciliationInstructions, ApplyResult
    from .contracts import (
        AssociationInstructionsByClaim,
        AssociationResolutionsByClaim,
        EntityInstructionsByClaim,
        EntityResolutionsByClaim,
        KeysByClaim,
        LinkInstructionsByClaim,
        LinkResolutionsByClaim,
        RepresentativesByClaim,
    )
    from .deduplicate import DeduplicateClaimGraph
    from .graph import ClaimGraph
    from .normalize import NormalizeClaimGraph
    from .persist import (
        PersistenceResult,
        PersistReconciliation,
        ReconciliationUnitOfWork,
    )
    from .policy import DecideApplyInstructions
    from .resolve import ResolveClaimGraph, ResolveRepositories


@dataclass(slots=True)
class PreparedReconciliation:
    """Stage outputs up to and including resolve."""

    graph: ClaimGraph
    keys_by_claim: KeysByClaim
    deduplicated_graph: ClaimGraph
    representatives_by_claim: RepresentativesByClaim
    entity_resolutions_by_claim: EntityResolutionsByClaim
    association_resolutions_by_claim: AssociationResolutionsByClaim
    link_resolutions_by_claim: LinkResolutionsByClaim


@dataclass(slots=True)
class ExecutedReconciliation:
    """Full stage outputs for one reconciliation run."""

    prepared: PreparedReconciliation
    entity_instructions_by_claim: EntityInstructionsByClaim
    association_instructions_by_claim: AssociationInstructionsByClaim
    link_instructions_by_claim: LinkInstructionsByClaim
    apply_result: ApplyResult
    persistence_result: PersistenceResult


@dataclass(slots=True)
class ReconciliationEngine:
    """Run full reconciliation from claim graph to persistence."""

    normalize: NormalizeClaimGraph
    deduplicate: DeduplicateClaimGraph
    resolve: ResolveClaimGraph
    decide: DecideApplyInstructions
    apply: ApplyReconciliationInstructions
    persist: PersistReconciliation

    @classmethod
    def default(cls) -> ReconciliationEngine:
        """Return the default production engine wiring."""

        return cls(
            normalize=normalize_claim_graph,
            deduplicate=deduplicate_claim_graph,
            resolve=resolve_claim_graph,
            decide=decide_apply_instructions,
            apply=apply_reconciliation_instructions,
            persist=persist_reconciliation,
        )

    def prepare(
        self,
        graph: ClaimGraph,
        *,
        repositories: ResolveRepositories,
    ) -> PreparedReconciliation:
        """Run normalize, deduplicate, and resolve for ``graph``."""

        keys_by_claim = self.normalize(graph)
        deduplicated_graph, representatives_by_claim = self.deduplicate(
            graph,
            keys_by_claim=keys_by_claim,
        )
        (
            entity_resolutions_by_claim,
            association_resolutions_by_claim,
            link_resolutions_by_claim,
        ) = self.resolve(
            deduplicated_graph,
            keys_by_claim=keys_by_claim,
            repositories=repositories,
        )
        return PreparedReconciliation(
            graph=graph,
            keys_by_claim=keys_by_claim,
            deduplicated_graph=deduplicated_graph,
            representatives_by_claim=representatives_by_claim,
            entity_resolutions_by_claim=entity_resolutions_by_claim,
            association_resolutions_by_claim=association_resolutions_by_claim,
            link_resolutions_by_claim=link_resolutions_by_claim,
        )

    def execute(
        self,
        prepared: PreparedReconciliation,
        *,
        uow: ReconciliationUnitOfWork,
    ) -> ExecutedReconciliation:
        """Run decide, apply, and persist for ``prepared``."""
        with uow.suspend_autoflush():
            (
                entity_instructions_by_claim,
                association_instructions_by_claim,
                link_instructions_by_claim,
            ) = self.decide(
                prepared.entity_resolutions_by_claim,
                prepared.association_resolutions_by_claim,
                prepared.link_resolutions_by_claim,
                graph=prepared.deduplicated_graph,
            )
            apply_result = self.apply(
                prepared.deduplicated_graph,
                entity_instructions_by_claim=entity_instructions_by_claim,
                association_instructions_by_claim=association_instructions_by_claim,
                link_instructions_by_claim=link_instructions_by_claim,
            )
            _prune_represented_entities(
                original_graph=prepared.graph,
                deduplicated_graph=prepared.deduplicated_graph,
                representatives_by_claim=prepared.representatives_by_claim,
            )
            persistence_result = self.persist(
                graph=prepared.deduplicated_graph,
                keys_by_claim=prepared.keys_by_claim,
                entity_instructions_by_claim=entity_instructions_by_claim,
                association_instructions_by_claim=association_instructions_by_claim,
                link_instructions_by_claim=link_instructions_by_claim,
                apply_result=apply_result,
                uow=uow,
            )
        return ExecutedReconciliation(
            prepared=prepared,
            entity_instructions_by_claim=entity_instructions_by_claim,
            association_instructions_by_claim=association_instructions_by_claim,
            link_instructions_by_claim=link_instructions_by_claim,
            apply_result=apply_result,
            persistence_result=persistence_result,
        )

    def reconcile(
        self,
        graph: ClaimGraph,
        *,
        uow: ReconciliationUnitOfWork,
    ) -> ExecutedReconciliation:
        """Run all reconciliation stages for ``graph``."""

        prepared = self.prepare(graph, repositories=uow.repositories)
        return self.execute(prepared, uow=uow)


def _prune_represented_entities(
    *,
    original_graph: ClaimGraph,
    deduplicated_graph: ClaimGraph,
    representatives_by_claim: RepresentativesByClaim,
) -> None:
    """Remove entity objects dropped by intra-batch dedup from mutable aggregates.

    Deduplication collapses claims, but the original entity objects still exist in the
    translated aggregate graph. Releases are the main problematic case because a dropped
    duplicate release can remain attached to a release set and later be flushed by ORM
    cascade, including its duplicate external IDs.
    """

    for original_claim_id, representative in representatives_by_claim.items():
        original_claim = original_graph.claim_for(original_claim_id)
        if original_claim is None:
            continue
        representative_claim = deduplicated_graph.claim_for(representative.claim_id)
        if representative_claim is None:
            continue
        match (original_claim.entity, representative_claim.entity):
            case (
                Release() as release,
                Release() as surviving_release,
            ) if release is not surviving_release:
                if release in release.release_set.releases:
                    release.release_set.remove_release(release)
            case _:
                pass
