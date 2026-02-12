from __future__ import annotations

from uuid import uuid4

import pytest

from sortipy.domain.model import Artist, Provider
from sortipy.domain.reconciliation import (
    ClaimGraph,
    ClaimMetadata,
    EntityClaim,
    RelationshipClaim,
    RelationshipKind,
)


def test_graph_rejects_relationship_with_missing_endpoint() -> None:
    artist_claim = EntityClaim(
        entity=Artist(name="Portishead"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(artist_claim)

    valid_relationship = RelationshipClaim(
        source_claim_id=artist_claim.claim_id,
        target_claim_id=artist_claim.claim_id,
        kind=RelationshipKind.RECORDING_CONTRIBUTION,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )

    graph.add_relationship(valid_relationship)
    graph.validate_invariants()

    with pytest.raises(ValueError, match="claim does not exist"):
        graph.add_relationship(
            valid_relationship.rewired(
                source_claim_id=artist_claim.claim_id,
                target_claim_id=uuid4(),
            )
        )
