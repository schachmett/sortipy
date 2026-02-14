from __future__ import annotations

from typing import TYPE_CHECKING

from sortipy.domain.model import Artist, ExternalNamespace, Provider, Recording
from sortipy.domain.reconciliation import ClaimGraph, ClaimMetadata, EntityClaim
from sortipy.domain.reconciliation.contracts import MatchKind, ResolutionStatus
from sortipy.domain.reconciliation.resolve import resolve_claim_graph

if TYPE_CHECKING:
    from sortipy.domain.reconciliation.contracts import KeysByClaim


def test_resolve_claim_graph_marks_new_when_no_exact_candidates() -> None:
    claim = EntityClaim(
        entity=Artist(name="Air"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(claim)

    keys_by_claim: KeysByClaim = {claim.claim_id: (("artist:name", "air"),)}
    resolutions_by_claim = resolve_claim_graph(graph, keys_by_claim=keys_by_claim)
    resolution = resolutions_by_claim.get(claim.claim_id)

    assert resolution is not None
    assert resolution.status is ResolutionStatus.NEW
    assert resolution.reason == "no_exact_match"


def test_resolve_claim_graph_marks_resolved_for_single_candidate() -> None:
    claim = EntityClaim(
        entity=Artist(name="Massive Attack"),
        metadata=ClaimMetadata(source=Provider.LASTFM),
    )
    graph = ClaimGraph()
    graph.add(claim)

    candidate = Artist(name="Massive Attack")
    resolutions_by_claim = resolve_claim_graph(
        graph,
        keys_by_claim={},
        find_exact_candidates=lambda _claim, _keys: (
            (candidate,),
            ("artist:name", "massive attack"),
        ),
    )
    resolution = resolutions_by_claim.get(claim.claim_id)

    assert resolution is not None
    assert resolution.status is ResolutionStatus.RESOLVED
    assert resolution.target == candidate
    assert resolution.match_kind is MatchKind.EXACT
    assert resolution.reason == "exact_match"


def test_resolve_claim_graph_marks_ambiguous_for_multiple_candidates() -> None:
    claim = EntityClaim(
        entity=Artist(name="Burial"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(claim)

    candidate_a = Artist(name="Burial")
    candidate_b = Artist(name="Burial")

    resolutions_by_claim = resolve_claim_graph(
        graph,
        keys_by_claim={},
        find_exact_candidates=lambda _claim, _keys: (
            (candidate_a, candidate_b),
            ("artist:name", "burial"),
        ),
    )
    resolution = resolutions_by_claim.get(claim.claim_id)

    assert resolution is not None
    assert resolution.status is ResolutionStatus.AMBIGUOUS
    assert resolution.candidates == (candidate_a, candidate_b)
    assert resolution.match_kind is MatchKind.EXACT
    assert resolution.reason == "multiple_exact_matches"


def test_resolve_claim_graph_marks_conflict_for_mismatched_candidate_type() -> None:
    claim = EntityClaim(
        entity=Artist(name="Portishead"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(claim)

    mismatched_candidate = Recording(title="Portishead")
    resolutions_by_claim = resolve_claim_graph(
        graph,
        keys_by_claim={},
        find_exact_candidates=lambda _claim, _keys: (
            (mismatched_candidate,),
            ("artist:name", "portishead"),
        ),
    )
    resolution = resolutions_by_claim.get(claim.claim_id)

    assert resolution is not None
    assert resolution.status is ResolutionStatus.CONFLICT
    assert resolution.match_kind is MatchKind.EXACT
    assert resolution.reason == "candidate_type_mismatch"


def test_resolve_claim_graph_forwards_normalization_keys_to_finder() -> None:
    claim = EntityClaim(
        entity=Artist(name="Skee Mask"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(claim)

    observed: dict[str, tuple[object, ...]] = {}
    keys = (("artist:name", "skee mask"), ("artist:source-name", Provider.SPOTIFY, "skee mask"))

    def _finder(
        _claim: EntityClaim, lookup_keys: tuple[tuple[object, ...], ...]
    ) -> tuple[tuple[Artist, ...], tuple[object, ...] | None]:
        observed["keys"] = lookup_keys
        return (), None

    keys_by_claim: KeysByClaim = {claim.claim_id: keys}
    resolutions_by_claim = resolve_claim_graph(
        graph,
        keys_by_claim=keys_by_claim,
        find_exact_candidates=_finder,
    )

    resolution = resolutions_by_claim.get(claim.claim_id)
    assert resolution is not None
    assert resolution.status is ResolutionStatus.NEW
    assert observed["keys"] == keys


def test_resolve_claim_graph_prefers_external_id_lookup_over_keys() -> None:
    artist = Artist(name="Boards of Canada")
    artist.add_external_id(
        ExternalNamespace.MUSICBRAINZ_ARTIST,
        "69158f97-a5af-4f2b-9f0f-7dcf6e3a1905",
    )
    claim = EntityClaim(
        entity=artist,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(claim)

    candidate = Artist(name="Boards of Canada")
    key_calls: list[tuple[object, ...]] = []

    def _by_external_id(_claim: EntityClaim, _namespace: object, _value: str) -> tuple[Artist, ...]:
        return (candidate,)

    def _by_normalized_key(_claim: EntityClaim, key: tuple[object, ...]) -> tuple[Artist, ...]:
        key_calls.append(key)
        return ()

    keys_by_claim: KeysByClaim = {
        claim.claim_id: (
            ("artist:name", "boards of canada"),
            ("artist:source-name", Provider.SPOTIFY, "boards of canada"),
        )
    }
    resolutions_by_claim = resolve_claim_graph(
        graph,
        keys_by_claim=keys_by_claim,
        find_by_external_id=_by_external_id,
        find_by_normalized_key=_by_normalized_key,
    )
    resolution = resolutions_by_claim.get(claim.claim_id)

    assert resolution is not None
    assert resolution.status is ResolutionStatus.RESOLVED
    assert resolution.target == candidate
    assert resolution.matched_key == (
        "external_id",
        ExternalNamespace.MUSICBRAINZ_ARTIST,
        "69158f97-a5af-4f2b-9f0f-7dcf6e3a1905",
    )
    assert key_calls == []


def test_resolve_claim_graph_falls_back_to_key_lookup_when_external_misses() -> None:
    artist = Artist(name="Autechre")
    artist.add_external_id(
        ExternalNamespace.MUSICBRAINZ_ARTIST,
        "9b4c6f95-a4f6-4e44-87b2-f845247e7a63",
    )
    claim = EntityClaim(
        entity=artist,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(claim)

    candidate = Artist(name="Autechre")
    observed_keys: list[tuple[object, ...]] = []

    def _by_external_id(_claim: EntityClaim, _namespace: object, _value: str) -> tuple[Artist, ...]:
        return ()

    def _by_normalized_key(_claim: EntityClaim, key: tuple[object, ...]) -> tuple[Artist, ...]:
        observed_keys.append(key)
        if key == ("artist:name", "autechre"):
            return (candidate,)
        return ()

    keys_by_claim: KeysByClaim = {
        claim.claim_id: (
            ("artist:name", "autechre"),
            ("artist:source-name", Provider.SPOTIFY, "autechre"),
        )
    }
    resolutions_by_claim = resolve_claim_graph(
        graph,
        keys_by_claim=keys_by_claim,
        find_by_external_id=_by_external_id,
        find_by_normalized_key=_by_normalized_key,
    )
    resolution = resolutions_by_claim.get(claim.claim_id)

    assert resolution is not None
    assert resolution.status is ResolutionStatus.RESOLVED
    assert resolution.target == candidate
    assert resolution.matched_key == ("artist:name", "autechre")
    assert observed_keys == [
        ("artist:name", "autechre"),
        ("artist:source-name", Provider.SPOTIFY, "autechre"),
    ]
