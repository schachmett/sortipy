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
from enum import Enum
from typing import TYPE_CHECKING, Protocol

from sortipy.domain.model import EntityType

from .graph import ClaimGraph
from .normalize import normalized_relationship_key

if TYPE_CHECKING:
    from uuid import UUID

    from .claims import EntityClaim, RelationshipClaim
    from .normalize import ClaimKey, NormalizationResult


@dataclass(slots=True)
class DeduplicationResult:
    """Result of intra-batch claim deduplication."""

    graph: ClaimGraph
    representative_by_claim: dict[UUID, UUID] = field(default_factory=dict["UUID", "UUID"])

    def representative_for(self, claim_id: UUID) -> UUID:
        return self.representative_by_claim.get(claim_id, claim_id)


class MissingRelationshipEndpointError(ValueError):
    """Raised when relationship rewiring points to non-existing entity claims."""

    def __init__(
        self,
        *,
        relationship_claim_id: UUID,
        endpoint: RelationshipEndpoint,
        endpoint_claim_id: UUID,
    ) -> None:
        self.relationship_claim_id = relationship_claim_id
        self.endpoint = endpoint
        self.endpoint_claim_id = endpoint_claim_id
        super().__init__(
            "Rewired relationship endpoint is missing from deduplicated graph: "
            f"relationship={relationship_claim_id}, "
            f"endpoint={endpoint.value}, "
            f"claim_id={endpoint_claim_id}"
        )


class RelationshipEndpoint(str, Enum):
    """Endpoint marker used by relationship rewiring exceptions."""

    SOURCE = "source"
    TARGET = "target"


class DeduplicateClaimGraph(Protocol):
    """Collapse duplicate claims in a graph."""

    def __call__(
        self,
        graph: ClaimGraph,
        *,
        normalization: NormalizationResult,
    ) -> DeduplicationResult: ...


def deduplicate_claim_graph(
    graph: ClaimGraph,
    *,
    normalization: NormalizationResult,
) -> DeduplicationResult:
    """Collapse duplicate claims and rewire relationship claims."""

    deduplicated_graph, representative_by_claim = _deduplicated_graph(
        graph,
        normalization=normalization,
    )
    return DeduplicationResult(
        graph=deduplicated_graph, representative_by_claim=representative_by_claim
    )


def _deduplicated_graph(
    graph: ClaimGraph,
    *,
    normalization: NormalizationResult,
) -> tuple[ClaimGraph, dict[UUID, UUID]]:
    deduplicated_graph = ClaimGraph()
    representative_by_claim: dict[UUID, UUID] = {}
    entity_key_index: dict[EntityType, dict[ClaimKey, UUID]] = {
        entity_type: {} for entity_type in EntityType
    }

    for claim in graph.claims:
        representative_id = _find_entity_representative(
            claim,
            key_index=entity_key_index,
            normalization=normalization,
        )
        if representative_id is None:
            deduplicated_graph.add(claim)
            _index_entity_claim_keys(
                claim,
                key_index=entity_key_index,
                normalization=normalization,
            )
            continue
        representative_by_claim[claim.claim_id] = representative_id

    for root_claim in graph.roots:
        representative_id = representative_by_claim.get(root_claim.claim_id, root_claim.claim_id)
        representative_claim = deduplicated_graph.claim_for(representative_id)
        if representative_claim is not None:
            deduplicated_graph.add_root(representative_claim)

    _deduplicate_relationship_claims(
        graph,
        deduplicated_graph=deduplicated_graph,
        representative_by_claim=representative_by_claim,
    )

    return deduplicated_graph, representative_by_claim


def _find_entity_representative(
    claim: EntityClaim,
    *,
    key_index: dict[EntityType, dict[ClaimKey, UUID]],
    normalization: NormalizationResult,
) -> UUID | None:
    keys = normalization.keys_by_claim.get(claim.claim_id, ())
    for key in keys:
        representative_id = key_index[claim.entity_type].get(key)
        if representative_id is not None:
            return representative_id
    return None


def _index_entity_claim_keys(
    claim: EntityClaim,
    *,
    key_index: dict[EntityType, dict[ClaimKey, UUID]],
    normalization: NormalizationResult,
) -> None:
    keys = normalization.keys_by_claim.get(claim.claim_id, ())
    for key in keys:
        key_index[claim.entity_type][key] = claim.claim_id


def _deduplicate_relationship_claims(
    graph: ClaimGraph,
    *,
    deduplicated_graph: ClaimGraph,
    representative_by_claim: dict[UUID, UUID],
) -> None:
    relationship_key_index: dict[ClaimKey, UUID] = {}

    for relationship in graph.relationships:
        rewired_relationship = _rewire_relationship(
            relationship,
            representative_by_claim=representative_by_claim,
        )

        if deduplicated_graph.claim_for(rewired_relationship.source_claim_id) is None:
            raise MissingRelationshipEndpointError(
                relationship_claim_id=relationship.claim_id,
                endpoint=RelationshipEndpoint.SOURCE,
                endpoint_claim_id=rewired_relationship.source_claim_id,
            )
        if deduplicated_graph.claim_for(rewired_relationship.target_claim_id) is None:
            raise MissingRelationshipEndpointError(
                relationship_claim_id=relationship.claim_id,
                endpoint=RelationshipEndpoint.TARGET,
                endpoint_claim_id=rewired_relationship.target_claim_id,
            )

        relationship_key = normalized_relationship_key(rewired_relationship)
        representative_id = relationship_key_index.get(relationship_key)
        if representative_id is None:
            deduplicated_graph.add_relationship(rewired_relationship)
            relationship_key_index[relationship_key] = rewired_relationship.claim_id
            continue

        representative_by_claim[relationship.claim_id] = representative_id


def _rewire_relationship(
    relationship: RelationshipClaim,
    *,
    representative_by_claim: dict[UUID, UUID],
) -> RelationshipClaim:
    source_claim_id = representative_by_claim.get(
        relationship.source_claim_id, relationship.source_claim_id
    )
    target_claim_id = representative_by_claim.get(
        relationship.target_claim_id, relationship.target_claim_id
    )
    return relationship.rewired(source_claim_id=source_claim_id, target_claim_id=target_claim_id)
