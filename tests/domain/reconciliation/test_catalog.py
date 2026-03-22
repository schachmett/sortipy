from __future__ import annotations

from sortipy.domain.model import Artist, ArtistRole, Provider, Recording, ReleaseSet
from sortipy.domain.reconciliation import (
    ApplyCounters,
    ApplyResult,
    Representative,
    build_catalog_claim_graph,
)


def test_build_catalog_claim_graph_tracks_entities_associations_and_roots() -> None:
    artist = Artist(name="Radiohead")
    release_set = ReleaseSet(title="OK Computer")
    contribution = release_set.add_artist(artist, role=ArtistRole.PRIMARY)
    release = release_set.create_release(title="OK Computer")
    recording = Recording(title="Airbag")
    track = release.add_track(recording, track_number=1)

    bundle = build_catalog_claim_graph(roots=(recording,), source=Provider.LASTFM)

    assert bundle.root_claim_ids == (bundle.require_entity_claim_id(recording),)
    assert bundle.graph.claim_for(bundle.require_entity_claim_id(artist)) is not None
    assert bundle.graph.claim_for(bundle.require_entity_claim_id(release_set)) is not None
    assert bundle.graph.claim_for(bundle.require_entity_claim_id(release)) is not None
    assert (
        bundle.graph.relationship_for(bundle.require_association_claim_id(contribution)) is not None
    )
    assert bundle.graph.relationship_for(bundle.require_association_claim_id(track)) is not None


def test_catalog_claim_graph_bundle_resolves_materialized_objects_via_representatives() -> None:
    artist = Artist(name="Aphex Twin")
    release_set = ReleaseSet(title="Selected Ambient Works 85-92")
    release_set.add_artist(artist, role=ArtistRole.PRIMARY)
    original = Recording(title="Xtal")
    duplicate = Recording(title="Xtal")
    release = release_set.create_release(title="Selected Ambient Works 85-92")
    release.add_track(original, track_number=1)

    bundle = build_catalog_claim_graph(roots=(original, duplicate), source=Provider.SPOTIFY)
    original_claim_id = bundle.require_entity_claim_id(original)
    duplicate_claim_id = bundle.require_entity_claim_id(duplicate)

    representatives_by_claim = {
        original_claim_id: Representative(claim_id=duplicate_claim_id),
    }
    apply_result = ApplyResult(
        entities=ApplyCounters(),
        associations=ApplyCounters(),
        links=ApplyCounters(),
        entities_by_claim={duplicate_claim_id: duplicate},
    )

    assert (
        bundle.representative_entity_claim_id(
            original,
            representatives_by_claim=representatives_by_claim,
        )
        == duplicate_claim_id
    )
    assert (
        bundle.require_materialized_entity(
            original,
            apply_result=apply_result,
            representatives_by_claim=representatives_by_claim,
        )
        is duplicate
    )
