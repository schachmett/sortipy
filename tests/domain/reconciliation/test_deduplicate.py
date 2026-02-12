from __future__ import annotations

import pytest

from sortipy.domain.model import Artist, Label, Provider, Recording, ReleaseSet
from sortipy.domain.reconciliation import (
    ClaimGraph,
    ClaimMetadata,
    EntityClaim,
    RelationshipClaim,
    RelationshipKind,
)
from sortipy.domain.reconciliation.deduplicate import (
    DefaultClaimDeduplicator,
    MissingRelationshipEndpointError,
    RelationshipEndpoint,
)
from sortipy.domain.reconciliation.normalize import NormalizationResult


def test_deduplicator_collapses_duplicate_claims_and_rewires_roots() -> None:
    first = EntityClaim(
        entity=Artist(name="Daft Punk"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    duplicate = EntityClaim(
        entity=Artist(name="Daft Punk"),
        metadata=ClaimMetadata(source=Provider.LASTFM),
    )

    graph = ClaimGraph()
    graph.add_root(first)
    graph.add_root(duplicate)

    normalization = NormalizationResult(
        keys_by_claim={
            first.claim_id: (("artist:name", "daft punk"),),
            duplicate.claim_id: (("artist:name", "daft punk"),),
        }
    )

    result = DefaultClaimDeduplicator().deduplicate(graph, normalization=normalization)

    assert tuple(claim.claim_id for claim in result.graph.claims) == (first.claim_id,)
    assert tuple(claim.claim_id for claim in result.graph.roots) == (first.claim_id,)
    assert result.representative_by_claim == {duplicate.claim_id: first.claim_id}
    assert result.representative_for(duplicate.claim_id) == first.claim_id


def test_deduplicator_does_not_collapse_across_entity_types() -> None:
    artist = EntityClaim(
        entity=Artist(name="Monolink"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    label = EntityClaim(
        entity=Label(name="Monolink"),
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )

    graph = ClaimGraph()
    graph.add(artist)
    graph.add(label)

    shared_key = ("name", "monolink")
    normalization = NormalizationResult(
        keys_by_claim={
            artist.claim_id: (shared_key,),
            label.claim_id: (shared_key,),
        }
    )

    result = DefaultClaimDeduplicator().deduplicate(graph, normalization=normalization)

    assert tuple(claim.claim_id for claim in result.graph.claims) == (
        artist.claim_id,
        label.claim_id,
    )
    assert result.representative_by_claim == {}


def test_deduplicator_keeps_claims_without_keys() -> None:
    first = EntityClaim(
        entity=Artist(name="No Key Artist"),
        metadata=ClaimMetadata(source=Provider.LASTFM),
    )
    second = EntityClaim(
        entity=Artist(name="No Key Artist"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )

    graph = ClaimGraph()
    graph.add(first)
    graph.add(second)

    normalization = NormalizationResult(
        keys_by_claim={
            first.claim_id: (),
            second.claim_id: (),
        }
    )

    result = DefaultClaimDeduplicator().deduplicate(graph, normalization=normalization)

    assert tuple(claim.claim_id for claim in result.graph.claims) == (
        first.claim_id,
        second.claim_id,
    )
    assert result.representative_by_claim == {}


def test_deduplicator_rewires_and_collapses_relationship_claims() -> None:
    release_set = ReleaseSet(title="Mezzanine")
    release = release_set.create_release(title="Mezzanine")
    recording_1 = Recording(title="Teardrop")
    recording_2 = Recording(title="Teardrop")

    release_claim = EntityClaim(
        entity=release,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    recording_claim_1 = EntityClaim(
        entity=recording_1,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    recording_claim_2 = EntityClaim(
        entity=recording_2,
        metadata=ClaimMetadata(source=Provider.LASTFM),
    )

    graph = ClaimGraph()
    graph.add(release_claim)
    graph.add(recording_claim_1)
    graph.add(recording_claim_2)

    relationship_1 = RelationshipClaim(
        source_claim_id=release_claim.claim_id,
        target_claim_id=recording_claim_1.claim_id,
        kind=RelationshipKind.RELEASE_TRACK,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    relationship_2 = RelationshipClaim(
        source_claim_id=release_claim.claim_id,
        target_claim_id=recording_claim_2.claim_id,
        kind=RelationshipKind.RELEASE_TRACK,
        metadata=ClaimMetadata(source=Provider.LASTFM),
    )
    graph.add_relationship(relationship_1)
    graph.add_relationship(relationship_2)

    normalization = NormalizationResult(
        keys_by_claim={
            release_claim.claim_id: (("release:title", "mezzanine"),),
            recording_claim_1.claim_id: (("recording:title", "teardrop"),),
            recording_claim_2.claim_id: (("recording:title", "teardrop"),),
        }
    )

    result = DefaultClaimDeduplicator().deduplicate(graph, normalization=normalization)

    assert len(result.graph.relationships) == 1
    surviving_relationship = result.graph.relationships[0]
    assert surviving_relationship.source_claim_id == release_claim.claim_id
    assert surviving_relationship.target_claim_id == recording_claim_1.claim_id
    assert result.representative_by_claim[recording_claim_2.claim_id] == recording_claim_1.claim_id
    assert result.representative_by_claim[relationship_2.claim_id] == relationship_1.claim_id


def test_deduplicator_collapses_non_payload_relationship_duplicates() -> None:
    release = EntityClaim(
        entity=ReleaseSet(title="Mezzanine").create_release(title="Mezzanine"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    label = EntityClaim(
        entity=Label(name="Virgin"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )

    graph = ClaimGraph()
    graph.add(release)
    graph.add(label)
    relationship_1 = RelationshipClaim(
        source_claim_id=release.claim_id,
        target_claim_id=label.claim_id,
        kind=RelationshipKind.RELEASE_LABEL,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    relationship_2 = RelationshipClaim(
        source_claim_id=release.claim_id,
        target_claim_id=label.claim_id,
        kind=RelationshipKind.RELEASE_LABEL,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    graph.add_relationship(relationship_1)
    graph.add_relationship(relationship_2)

    normalization = NormalizationResult(
        keys_by_claim={
            release.claim_id: (("release:title", "mezzanine"),),
            label.claim_id: (("label:name", "virgin"),),
        }
    )
    result = DefaultClaimDeduplicator().deduplicate(graph, normalization=normalization)

    assert len(result.graph.relationships) == 1
    assert result.graph.relationships[0].claim_id == relationship_1.claim_id
    assert result.representative_by_claim[relationship_2.claim_id] == relationship_1.claim_id


def test_deduplicator_rewires_one_to_many_ownership_relationships() -> None:
    release_set_1 = EntityClaim(
        entity=ReleaseSet(title="Moon Safari"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    release_set_2 = EntityClaim(
        entity=ReleaseSet(title="Moon Safari"),
        metadata=ClaimMetadata(source=Provider.LASTFM),
    )
    release = EntityClaim(
        entity=ReleaseSet(title="Moon Safari").create_release(title="Moon Safari"),
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )

    graph = ClaimGraph()
    graph.add(release_set_1)
    graph.add(release_set_2)
    graph.add(release)
    ownership = RelationshipClaim(
        source_claim_id=release_set_2.claim_id,
        target_claim_id=release.claim_id,
        kind=RelationshipKind.RELEASE_SET_RELEASE,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    graph.add_relationship(ownership)

    normalization = NormalizationResult(
        keys_by_claim={
            release_set_1.claim_id: (("release_set:title", "moon safari"),),
            release_set_2.claim_id: (("release_set:title", "moon safari"),),
            release.claim_id: (("release:title", "moon safari"),),
        }
    )
    result = DefaultClaimDeduplicator().deduplicate(graph, normalization=normalization)

    assert len(result.graph.relationships) == 1
    rewired = result.graph.relationships[0]
    assert rewired.source_claim_id == release_set_1.claim_id
    assert rewired.target_claim_id == release.claim_id


def test_deduplicator_raises_for_relationships_with_missing_rewired_endpoints() -> None:
    artist_claim = EntityClaim(
        entity=Artist(name="Air"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(artist_claim)

    bad_relationship = RelationshipClaim(
        source_claim_id=artist_claim.claim_id,
        target_claim_id=artist_claim.claim_id,
        kind=RelationshipKind.RELEASE_LABEL,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph._relationship_claims_by_id[bad_relationship.claim_id] = bad_relationship
    graph._relationship_claim_ids_by_kind[RelationshipKind.RELEASE_LABEL].append(
        bad_relationship.claim_id
    )
    graph._relationship_claims_by_id[bad_relationship.claim_id] = bad_relationship.rewired(
        source_claim_id=artist_claim.claim_id,
        target_claim_id=bad_relationship.claim_id,
    )

    normalization = NormalizationResult(
        keys_by_claim={artist_claim.claim_id: (("artist:name", "air"),)}
    )

    with pytest.raises(MissingRelationshipEndpointError) as exc_info:
        DefaultClaimDeduplicator().deduplicate(graph, normalization=normalization)

    assert exc_info.value.endpoint == RelationshipEndpoint.TARGET
    assert exc_info.value.relationship_claim_id == bad_relationship.claim_id
    assert exc_info.value.endpoint_claim_id == bad_relationship.claim_id
