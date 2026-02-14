from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

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
from sortipy.domain.reconciliation.claims import RelationshipClaim, RelationshipKind
from sortipy.domain.reconciliation.normalize import (
    normalize_claim_graph,
    normalized_relationship_key,
)

if TYPE_CHECKING:
    import pytest


def test_normalizer_computes_artist_keys_deterministically() -> None:
    artist = Artist(name="R.E.M.!")
    artist.add_source(Provider.SPOTIFY)
    artist.add_source(Provider.LASTFM)
    artist.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, "mbid-artist-1")

    claim = EntityClaim(entity=artist, metadata=ClaimMetadata(source=Provider.LASTFM))
    graph = ClaimGraph()
    graph.add(claim)

    first = normalize_claim_graph(graph)[claim.claim_id]
    second = normalize_claim_graph(graph)[claim.claim_id]

    assert first == second
    assert first == (
        ("artist:external_id", str(ExternalNamespace.MUSICBRAINZ_ARTIST), "mbid-artist-1"),
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

    keys_1 = normalize_claim_graph(graph_1)[claim_1.claim_id]
    keys_2 = normalize_claim_graph(graph_2)[claim_2.claim_id]

    assert keys_1 == keys_2
    assert keys_1 == (("artist:name", "boards of canada"),)


def test_release_set_normalization_uses_primary_artist_priority() -> None:
    release_set = ReleaseSet(title="Kid A")
    release_set.add_artist(Artist(name="Featured Artist"), role=ArtistRole.FEATURED, credit_order=0)
    release_set.add_artist(Artist(name="Radiohead"), role=ArtistRole.PRIMARY, credit_order=1)

    claim = EntityClaim(entity=release_set, metadata=ClaimMetadata(source=Provider.MUSICBRAINZ))
    graph = ClaimGraph()
    graph.add(claim)

    keys = normalize_claim_graph(graph)[claim.claim_id]

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

    keys = normalize_claim_graph(graph)[claim.claim_id]

    assert (
        "play_event:user-source-played_at",
        ("user:display_name", "listener"),
        Provider.LASTFM,
        played_at,
    ) in keys
    assert (
        "play_event:recording-played_at",
        ("recording:artist-title", "massive attack", "teardrop"),
        played_at,
    ) in keys
    assert (
        "play_event:track-played_at",
        (
            "release_track:release-recording",
            ("release:artist-title", "massive attack", "mezzanine"),
            ("recording:artist-title", "massive attack", "teardrop"),
        ),
        played_at,
    ) in keys


def test_relationship_key_normalizes_contribution_payload() -> None:
    artist = Artist(name="Massive Attack")
    recording = Recording(title="Teardrop")
    contribution = recording.add_artist(
        artist,
        role=ArtistRole.FEATURED,
        credit_order=2,
        credited_as="Liz Fraser",
        join_phrase=" feat. ",
    )

    source_claim = EntityClaim(
        entity=recording,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    target_claim = EntityClaim(
        entity=artist,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )

    relationship_claim = RelationshipClaim(
        source_claim_id=source_claim.claim_id,
        target_claim_id=target_claim.claim_id,
        kind=RelationshipKind.RECORDING_CONTRIBUTION,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
        payload=contribution,
    )

    key = normalized_relationship_key(relationship_claim)

    assert key[0] == "relationship"
    assert key[1] == RelationshipKind.RECORDING_CONTRIBUTION
    assert key[2] == source_claim.claim_id
    assert key[3] == target_claim.claim_id
    assert key[4:] == (ArtistRole.FEATURED, 2, "liz fraser", "feat")


def test_normalizer_logs_warning_for_claim_without_any_keys(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("WARNING")

    user = User(display_name="")
    claim = EntityClaim(entity=user, metadata=ClaimMetadata(source=Provider.SPOTIFY))
    graph = ClaimGraph()
    graph.add(claim)

    keys_by_claim = normalize_claim_graph(graph)

    assert keys_by_claim[claim.claim_id] == ()
    assert "No normalization keys" in caplog.text
