from __future__ import annotations

from datetime import UTC, datetime

from sortipy.domain.model import (
    Artist,
    ArtistRole,
    ExternalNamespace,
    Provider,
    Recording,
    ReleaseSet,
    User,
)
from sortipy.domain.reconciliation import ClaimEvidence, ClaimGraph, ClaimMetadata, EntityClaim
from sortipy.domain.reconciliation.normalize import DefaultClaimNormalizer


def test_normalizer_computes_artist_keys_deterministically() -> None:
    artist = Artist(name="R.E.M.!")
    artist.add_source(Provider.SPOTIFY)
    artist.add_source(Provider.LASTFM)
    artist.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, "mbid-artist-1")

    claim = EntityClaim(entity=artist, metadata=ClaimMetadata(source=Provider.LASTFM))
    graph = ClaimGraph()
    graph.add(claim)

    normalizer = DefaultClaimNormalizer()
    first = normalizer.normalize(graph).keys_by_claim[claim.claim_id]
    second = normalizer.normalize(graph).keys_by_claim[claim.claim_id]

    assert first == second
    assert first == (
        ("artist:mbid", "mbid-artist-1"),
        ("artist:source-name", Provider.LASTFM, "rem"),
        ("artist:name", "rem"),
    )


def test_normalizer_ignores_claim_metadata_and_evidence_for_keys() -> None:
    artist_1 = Artist(name="Boards of Canada")
    artist_2 = Artist(name="Boards of Canada")

    claim_1 = EntityClaim(
        entity=artist_1,
        metadata=ClaimMetadata(source=Provider.LASTFM, confidence=0.1),
        evidence=ClaimEvidence(values={"score": 12, "provider_note": "x"}),
    )
    claim_2 = EntityClaim(
        entity=artist_2,
        metadata=ClaimMetadata(source=Provider.SPOTIFY, confidence=0.99),
        evidence=ClaimEvidence(values={"score": 999, "provider_note": "y"}),
    )

    graph_1 = ClaimGraph()
    graph_1.add(claim_1)
    graph_2 = ClaimGraph()
    graph_2.add(claim_2)

    normalizer = DefaultClaimNormalizer()
    keys_1 = normalizer.normalize(graph_1).keys_by_claim[claim_1.claim_id]
    keys_2 = normalizer.normalize(graph_2).keys_by_claim[claim_2.claim_id]

    assert keys_1 == keys_2
    assert keys_1 == (("artist:name", "boards of canada"),)


def test_release_set_normalization_uses_primary_artist_priority() -> None:
    release_set = ReleaseSet(title="Kid A")
    release_set.add_artist(Artist(name="Featured Artist"), role=ArtistRole.FEATURED, credit_order=0)
    release_set.add_artist(Artist(name="Radiohead"), role=ArtistRole.PRIMARY, credit_order=1)

    claim = EntityClaim(entity=release_set, metadata=ClaimMetadata(source=Provider.MUSICBRAINZ))
    graph = ClaimGraph()
    graph.add(claim)

    keys = DefaultClaimNormalizer().normalize(graph).keys_by_claim[claim.claim_id]

    assert ("release_set:artist-title", "radiohead", "kid a") in keys
    assert ("release_set:artist-title", "featured artist", "kid a") not in keys


def test_play_event_normalization_includes_track_key_when_available() -> None:
    user = User(display_name="listener")
    artist = Artist(name="Massive Attack")
    recording = Recording(title="Teardrop")
    recording.add_artist(artist, role=ArtistRole.PRIMARY, credit_order=0)

    release_set = ReleaseSet(title="Mezzanine")
    release_set.add_artist(artist, role=ArtistRole.PRIMARY, credit_order=0)
    release = release_set.create_release(title="Mezzanine")
    track = release.add_track(recording, disc_number=1, track_number=2)

    played_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    event = user.log_play(
        played_at=played_at,
        source=Provider.LASTFM,
        recording=recording,
        track=track,
    )

    claim = EntityClaim(entity=event, metadata=ClaimMetadata(source=Provider.LASTFM))
    graph = ClaimGraph()
    graph.add(claim)

    keys = DefaultClaimNormalizer().normalize(graph).keys_by_claim[claim.claim_id]

    assert (
        "play_event:user-source-played_at",
        user.resolved_id,
        Provider.LASTFM,
        played_at,
    ) in keys
    assert ("play_event:recording-played_at", recording.resolved_id, played_at) in keys
    assert ("play_event:track-played_at", track.resolved_id, played_at) in keys
