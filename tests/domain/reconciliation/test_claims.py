from __future__ import annotations

import pytest

from sortipy.domain.model import Artist, Provider, Recording
from sortipy.domain.reconciliation import ClaimMetadata, EntityClaim


def test_entity_claim_rejects_association_entities() -> None:
    artist = Artist(name="Massive Attack")
    recording = Recording(title="Teardrop")
    contribution = recording.add_artist(artist)

    with pytest.raises(TypeError, match="Association entities must be modeled"):
        EntityClaim(
            entity=contribution,  # pyright: ignore[reportArgumentType]
            metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
        )
