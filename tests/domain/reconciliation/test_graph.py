from __future__ import annotations

from uuid import uuid4

import pytest

from sortipy.domain.model import Artist, Provider
from sortipy.domain.reconciliation import (
    AssociationClaim,
    AssociationKind,
    ClaimGraph,
    ClaimMetadata,
    EntityClaim,
    LinkClaim,
    LinkKind,
)


def test_graph_rejects_relationship_with_missing_endpoint() -> None:
    artist_claim = EntityClaim(
        entity=Artist(name="Portishead"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(artist_claim)

    valid_relationship = AssociationClaim(
        source_claim_id=artist_claim.claim_id,
        target_claim_id=artist_claim.claim_id,
        kind=AssociationKind.RECORDING_CONTRIBUTION,
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


def test_graph_require_helpers_return_typed_claims() -> None:
    artist_claim = EntityClaim(
        entity=Artist(name="Portishead"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    link_claim = LinkClaim(
        source_claim_id=artist_claim.claim_id,
        target_claim_id=artist_claim.claim_id,
        kind=LinkKind.USER_PLAY_EVENT,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )

    graph = ClaimGraph()
    graph.add(artist_claim)
    graph.add_relationship(link_claim)

    assert graph.require_claim(artist_claim.claim_id) is artist_claim
    assert graph.require_link(link_claim.claim_id) is link_claim

    with pytest.raises(TypeError, match="Expected association claim"):
        graph.require_association(link_claim.claim_id)
