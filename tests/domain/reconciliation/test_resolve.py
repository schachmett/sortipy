from __future__ import annotations

from typing import TYPE_CHECKING

from sortipy.domain.model import Artist, Provider, Recording
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
        find_exact_candidates=lambda _claim, _keys: (candidate, candidate),
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
        find_exact_candidates=lambda _claim, _keys: (candidate_a, candidate_b),
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
        find_exact_candidates=lambda _claim, _keys: (mismatched_candidate,),
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
    ) -> tuple[Artist, ...]:
        observed["keys"] = lookup_keys
        return ()

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
