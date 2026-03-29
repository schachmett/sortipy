from __future__ import annotations

from typing import TYPE_CHECKING, cast

from sortipy.domain.model import (
    Artist,
    ExternalNamespace,
    Label,
    Provider,
    Recording,
    ReleaseSet,
    User,
)
from sortipy.domain.reconciliation import (
    AssociationClaim,
    AssociationKind,
    ClaimGraph,
    ClaimMetadata,
    EntityClaim,
    LinkClaim,
    LinkKind,
)
from sortipy.domain.reconciliation.contracts import (
    LinkResolvedResolution,
    MatchKind,
    ResolutionStatus,
)
from sortipy.domain.reconciliation.resolve import resolve_claim_graph

if TYPE_CHECKING:
    from sortipy.domain.reconciliation.contracts import KeysByClaim
    from sortipy.domain.reconciliation.resolve import ResolveRepositories


def test_resolve_claim_graph_marks_new_when_no_exact_candidates() -> None:
    claim = EntityClaim(
        entity=Artist(name="Air"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(claim)

    keys_by_claim: KeysByClaim = {claim.claim_id: (("artist:name", "air"),)}
    (
        entity_resolutions_by_claim,
        association_resolutions_by_claim,
        link_resolutions_by_claim,
    ) = resolve_claim_graph(
        graph,
        keys_by_claim=keys_by_claim,
    )
    resolution = entity_resolutions_by_claim.get(claim.claim_id)

    assert resolution is not None
    assert resolution.status is ResolutionStatus.NEW
    assert resolution.reason == "no_exact_match"
    assert association_resolutions_by_claim == {}
    assert link_resolutions_by_claim == {}


def test_resolve_claim_graph_marks_resolved_for_single_candidate() -> None:
    claim = EntityClaim(
        entity=Artist(name="Massive Attack"),
        metadata=ClaimMetadata(source=Provider.LASTFM),
    )
    graph = ClaimGraph()
    graph.add(claim)

    candidate = Artist(name="Massive Attack")
    keys_by_claim: KeysByClaim = {claim.claim_id: (("artist:name", "massive attack"),)}
    (
        entity_resolutions_by_claim,
        association_resolutions_by_claim,
        link_resolutions_by_claim,
    ) = resolve_claim_graph(
        graph,
        keys_by_claim=keys_by_claim,
        find_by_normalized_key=lambda _claim, key: (
            (candidate,) if key[1] == "massive attack" else ()
        ),
    )
    resolution = entity_resolutions_by_claim.get(claim.claim_id)

    assert resolution is not None
    assert resolution.status is ResolutionStatus.RESOLVED
    assert resolution.target == candidate
    assert resolution.match_kind is MatchKind.EXACT
    assert resolution.reason == "exact_match"
    assert association_resolutions_by_claim == {}
    assert link_resolutions_by_claim == {}


def test_resolve_claim_graph_marks_ambiguous_for_multiple_candidates() -> None:
    claim = EntityClaim(
        entity=Artist(name="Burial"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(claim)

    candidate_a = Artist(name="Burial")
    candidate_b = Artist(name="Burial")
    keys_by_claim: KeysByClaim = {claim.claim_id: (("artist:name", "burial"),)}

    (
        entity_resolutions_by_claim,
        association_resolutions_by_claim,
        link_resolutions_by_claim,
    ) = resolve_claim_graph(
        graph,
        keys_by_claim=keys_by_claim,
        find_by_normalized_key=lambda _claim, key: (
            (candidate_a, candidate_b) if key[1] == "burial" else ()
        ),
    )
    resolution = entity_resolutions_by_claim.get(claim.claim_id)

    assert resolution is not None
    assert resolution.status is ResolutionStatus.AMBIGUOUS
    assert resolution.candidates == (candidate_a, candidate_b)
    assert resolution.match_kind is MatchKind.EXACT
    assert resolution.reason == "multiple_exact_matches"
    assert association_resolutions_by_claim == {}
    assert link_resolutions_by_claim == {}


def test_resolve_claim_graph_marks_conflict_for_mismatched_candidate_type() -> None:
    claim = EntityClaim(
        entity=Artist(name="Portishead"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(claim)

    mismatched_candidate = Recording(title="Portishead")
    keys_by_claim: KeysByClaim = {claim.claim_id: (("artist:name", "portishead"),)}
    (
        entity_resolutions_by_claim,
        association_resolutions_by_claim,
        link_resolutions_by_claim,
    ) = resolve_claim_graph(
        graph,
        keys_by_claim=keys_by_claim,
        find_by_normalized_key=lambda _claim, key: (
            (mismatched_candidate,) if key[1] == "portishead" else ()
        ),
    )
    resolution = entity_resolutions_by_claim.get(claim.claim_id)

    assert resolution is not None
    assert resolution.status is ResolutionStatus.CONFLICT
    assert resolution.match_kind is MatchKind.EXACT
    assert resolution.reason == "candidate_type_mismatch"
    assert association_resolutions_by_claim == {}
    assert link_resolutions_by_claim == {}


def test_resolve_claim_graph_marks_conflict_for_external_id_namespace_collision() -> None:
    claim_recording = Recording(title="Man Made of Meat")
    claim_recording.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RECORDING,
        "incoming-mbid",
    )
    claim = EntityClaim(
        entity=claim_recording,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    graph = ClaimGraph()
    graph.add(claim)

    candidate = Recording(title="Man Made of Meat")
    candidate.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RECORDING,
        "canonical-mbid",
    )
    keys_by_claim: KeysByClaim = {claim.claim_id: (("recording:title", "man made of meat"),)}
    (
        entity_resolutions_by_claim,
        association_resolutions_by_claim,
        link_resolutions_by_claim,
    ) = resolve_claim_graph(
        graph,
        keys_by_claim=keys_by_claim,
        find_by_normalized_key=lambda _claim, key: (
            (candidate,) if key[1] == "man made of meat" else ()
        ),
    )
    resolution = entity_resolutions_by_claim.get(claim.claim_id)

    assert resolution is not None
    assert resolution.status is ResolutionStatus.CONFLICT
    assert resolution.match_kind is MatchKind.EXACT
    assert resolution.reason == "external_id_namespace_conflict"
    assert association_resolutions_by_claim == {}
    assert link_resolutions_by_claim == {}


def test_resolve_claim_graph_rejects_exact_match_when_another_namespace_conflicts() -> None:
    claim_recording = Recording(title="Man Made of Meat")
    claim_recording.add_external_id(
        ExternalNamespace.LASTFM_RECORDING,
        "https://www.last.fm/music/Viagra+Boys/_/Man+Made+of+Meat",
    )
    claim_recording.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RECORDING,
        "incoming-mbid",
    )
    claim = EntityClaim(
        entity=claim_recording,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    graph = ClaimGraph()
    graph.add(claim)

    candidate = Recording(title="Man Made of Meat")
    candidate.add_external_id(
        ExternalNamespace.LASTFM_RECORDING,
        "https://www.last.fm/music/Viagra+Boys/_/Man+Made+of+Meat",
    )
    candidate.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RECORDING,
        "canonical-mbid",
    )
    keys_by_claim: KeysByClaim = {claim.claim_id: (("recording:title", "man made of meat"),)}
    (
        entity_resolutions_by_claim,
        association_resolutions_by_claim,
        link_resolutions_by_claim,
    ) = resolve_claim_graph(
        graph,
        keys_by_claim=keys_by_claim,
        find_by_external_id=lambda _claim, namespace, value: (
            (candidate,)
            if namespace is ExternalNamespace.LASTFM_RECORDING
            and value == "https://www.last.fm/music/Viagra+Boys/_/Man+Made+of+Meat"
            else ()
        ),
    )
    resolution = entity_resolutions_by_claim.get(claim.claim_id)

    assert resolution is not None
    assert resolution.status is ResolutionStatus.CONFLICT
    assert resolution.match_kind is MatchKind.EXACT
    assert resolution.reason == "external_id_namespace_conflict"
    assert resolution.matched_key == (
        "external_id",
        ExternalNamespace.LASTFM_RECORDING,
        "https://www.last.fm/music/Viagra+Boys/_/Man+Made+of+Meat",
    )
    assert association_resolutions_by_claim == {}
    assert link_resolutions_by_claim == {}


def test_resolve_claim_graph_forwards_normalization_keys_to_finder() -> None:
    claim = EntityClaim(
        entity=Artist(name="Skee Mask"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(claim)

    observed_keys: list[tuple[object, ...]] = []
    keys = (("artist:name", "skee mask"), ("artist:source-name", Provider.SPOTIFY, "skee mask"))

    def _by_normalized_key(_claim: EntityClaim, key: tuple[object, ...]) -> tuple[Artist, ...]:
        observed_keys.append(key)
        return ()

    keys_by_claim: KeysByClaim = {claim.claim_id: keys}
    (
        entity_resolutions_by_claim,
        association_resolutions_by_claim,
        link_resolutions_by_claim,
    ) = resolve_claim_graph(
        graph,
        keys_by_claim=keys_by_claim,
        find_by_normalized_key=_by_normalized_key,
    )

    resolution = entity_resolutions_by_claim.get(claim.claim_id)
    assert resolution is not None
    assert resolution.status is ResolutionStatus.NEW
    assert observed_keys == list(keys)
    assert association_resolutions_by_claim == {}
    assert link_resolutions_by_claim == {}


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
    (
        entity_resolutions_by_claim,
        association_resolutions_by_claim,
        link_resolutions_by_claim,
    ) = resolve_claim_graph(
        graph,
        keys_by_claim=keys_by_claim,
        find_by_external_id=_by_external_id,
        find_by_normalized_key=_by_normalized_key,
    )
    resolution = entity_resolutions_by_claim.get(claim.claim_id)

    assert resolution is not None
    assert resolution.status is ResolutionStatus.RESOLVED
    assert resolution.target == candidate
    assert resolution.matched_key == (
        "external_id",
        ExternalNamespace.MUSICBRAINZ_ARTIST,
        "69158f97-a5af-4f2b-9f0f-7dcf6e3a1905",
    )
    assert key_calls == []
    assert association_resolutions_by_claim == {}
    assert link_resolutions_by_claim == {}


def test_resolve_claim_graph_uses_repository_backed_lookup_when_provided() -> None:
    claim = EntityClaim(
        entity=Artist(name="Autechre"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(claim)

    candidate = Artist(name="Autechre")
    key = ("artist:name", "autechre")
    keys_by_claim: KeysByClaim = {claim.claim_id: (key,)}

    class _ArtistRepository:
        def get_by_external_id(self, _namespace: object, _value: str) -> Artist | None:
            return None

    class _NullRepository:
        def get_by_external_id(self, _namespace: object, _value: str) -> object | None:
            return None

    class _NormalizationSidecars:
        def save(self, _entity: object, _data: object) -> None:
            return None

        def find_by_keys(
            self,
            _entity_type: object,
            keys: tuple[tuple[object, ...], ...],
        ) -> dict[tuple[object, ...], object]:
            if key in keys:
                return {key: candidate}
            return {}

    class _NullExternalIdRedirectRepository:
        def save_redirect(
            self,
            namespace: object,
            source_value: str,
            target_value: str,
            *,
            provider: object | None = None,
        ) -> None:
            _ = (namespace, source_value, target_value, provider)

        def resolve(self, namespace: object, value: str) -> None:
            _ = (namespace, value)

    class _Repositories:
        def __init__(self) -> None:
            self.artists = _ArtistRepository()
            self.labels = _NullRepository()
            self.release_sets = _NullRepository()
            self.releases = _NullRepository()
            self.recordings = _NullRepository()
            self.normalization_sidecars = _NormalizationSidecars()
            self.external_id_redirects = _NullExternalIdRedirectRepository()

    (
        entity_resolutions_by_claim,
        association_resolutions_by_claim,
        link_resolutions_by_claim,
    ) = resolve_claim_graph(
        graph,
        keys_by_claim=keys_by_claim,
        repositories=cast("ResolveRepositories", _Repositories()),
    )
    resolution = entity_resolutions_by_claim.get(claim.claim_id)

    assert resolution is not None
    assert resolution.status is ResolutionStatus.RESOLVED
    assert resolution.target == candidate
    assert resolution.matched_key == key
    assert association_resolutions_by_claim == {}
    assert link_resolutions_by_claim == {}


def test_resolve_claim_graph_uses_sidecar_lookup_for_user_claim() -> None:
    claim = EntityClaim(
        entity=User(display_name="alice", email="alice@example.com"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(claim)

    candidate = User(display_name="Alice", email="alice@example.com")
    key = ("user:email", "alice@example.com")
    keys_by_claim: KeysByClaim = {claim.claim_id: (key,)}

    class _NullRepository:
        def get_by_external_id(self, _namespace: object, _value: str) -> object | None:
            return None

    class _NormalizationSidecars:
        def save(self, _entity: object, _data: object) -> None:
            return None

        def find_by_keys(
            self,
            _entity_type: object,
            keys: tuple[tuple[object, ...], ...],
        ) -> dict[tuple[object, ...], object]:
            if key in keys:
                return {key: candidate}
            return {}

    class _NullExternalIdRedirectRepository:
        def save_redirect(
            self,
            namespace: object,
            source_value: str,
            target_value: str,
            *,
            provider: object | None = None,
        ) -> None:
            _ = (namespace, source_value, target_value, provider)

        def resolve(self, namespace: object, value: str) -> None:
            _ = (namespace, value)

    class _Repositories:
        def __init__(self) -> None:
            self.artists = _NullRepository()
            self.labels = _NullRepository()
            self.release_sets = _NullRepository()
            self.releases = _NullRepository()
            self.recordings = _NullRepository()
            self.normalization_sidecars = _NormalizationSidecars()
            self.external_id_redirects = _NullExternalIdRedirectRepository()

    (
        entity_resolutions_by_claim,
        association_resolutions_by_claim,
        link_resolutions_by_claim,
    ) = resolve_claim_graph(
        graph,
        keys_by_claim=keys_by_claim,
        repositories=cast("ResolveRepositories", _Repositories()),
    )
    resolution = entity_resolutions_by_claim.get(claim.claim_id)

    assert resolution is not None
    assert resolution.status is ResolutionStatus.RESOLVED
    assert resolution.target == candidate
    assert resolution.matched_key == key
    assert association_resolutions_by_claim == {}
    assert link_resolutions_by_claim == {}


def test_resolve_claim_graph_falls_back_through_external_id_redirects() -> None:
    claim_release = ReleaseSet(title="BLUSH").create_release(title="BLUSH")
    claim_release.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RELEASE,
        "e6b9c875-f521-4261-892b-b0318a1b9b1b",
    )
    claim = EntityClaim(
        entity=claim_release,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    graph = ClaimGraph()
    graph.add(claim)

    candidate_release = ReleaseSet(title="BLUSH").create_release(title="BLUSH")
    candidate_release.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RELEASE,
        "0772539c-7916-4504-bfdd-3ea8e011bb4d",
    )

    class _NullRepository:
        def get_by_external_id(self, _namespace: object, _value: str) -> object | None:
            return None

    class _ReleaseRepository:
        def get_by_external_id(self, namespace: object, value: str) -> object | None:
            if (
                namespace is ExternalNamespace.MUSICBRAINZ_RELEASE
                and value == "0772539c-7916-4504-bfdd-3ea8e011bb4d"
            ):
                return candidate_release
            return None

    class _NormalizationSidecars:
        def save(self, _entity: object, _data: object) -> None:
            return None

        def find_by_keys(
            self,
            _entity_type: object,
            _keys: tuple[tuple[object, ...], ...],
        ) -> dict[tuple[object, ...], object]:
            return {}

    class _ExternalIdRedirects:
        def save_redirect(
            self,
            namespace: object,
            source_value: str,
            target_value: str,
            *,
            provider: object | None = None,
        ) -> None:
            _ = (namespace, source_value, target_value, provider)

        def resolve(self, namespace: object, value: str) -> str | None:
            if (
                namespace is ExternalNamespace.MUSICBRAINZ_RELEASE
                and value == "e6b9c875-f521-4261-892b-b0318a1b9b1b"
            ):
                return "0772539c-7916-4504-bfdd-3ea8e011bb4d"
            return None

    class _Repositories:
        def __init__(self) -> None:
            self.artists = _NullRepository()
            self.labels = _NullRepository()
            self.release_sets = _NullRepository()
            self.releases = _ReleaseRepository()
            self.recordings = _NullRepository()
            self.normalization_sidecars = _NormalizationSidecars()
            self.external_id_redirects = _ExternalIdRedirects()

    (
        entity_resolutions_by_claim,
        association_resolutions_by_claim,
        link_resolutions_by_claim,
    ) = resolve_claim_graph(
        graph,
        keys_by_claim={},
        repositories=cast("ResolveRepositories", _Repositories()),
    )
    resolution = entity_resolutions_by_claim.get(claim.claim_id)

    assert resolution is not None
    assert resolution.status is ResolutionStatus.RESOLVED
    assert resolution.target == candidate_release
    assert resolution.matched_key == (
        "external_id",
        ExternalNamespace.MUSICBRAINZ_RELEASE,
        "e6b9c875-f521-4261-892b-b0318a1b9b1b",
    )
    assert association_resolutions_by_claim == {}
    assert link_resolutions_by_claim == {}


def test_resolve_claim_graph_marks_association_new_when_not_found() -> None:
    release_set_claim = EntityClaim(
        entity=ReleaseSet(title="Source"),
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    artist_claim = EntityClaim(
        entity=Artist(name="Target"),
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    association_claim = AssociationClaim(
        source_claim_id=release_set_claim.claim_id,
        target_claim_id=artist_claim.claim_id,
        kind=AssociationKind.RELEASE_SET_CONTRIBUTION,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )

    graph = ClaimGraph()
    graph.add(release_set_claim)
    graph.add(artist_claim)
    graph.add_relationship(association_claim)

    _, association_resolutions_by_claim, _ = resolve_claim_graph(graph, keys_by_claim={})
    association_resolution = association_resolutions_by_claim.get(association_claim.claim_id)

    assert association_resolution is not None
    assert association_resolution.status is ResolutionStatus.NEW


def test_resolve_claim_graph_marks_association_resolved_when_existing_payload_found() -> None:
    release_set = ReleaseSet(title="Source")
    artist = Artist(name="Target")
    contribution = release_set.add_artist(artist)

    release_set_claim = EntityClaim(
        entity=release_set,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    artist_claim = EntityClaim(
        entity=artist,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    association_claim = AssociationClaim(
        source_claim_id=release_set_claim.claim_id,
        target_claim_id=artist_claim.claim_id,
        kind=AssociationKind.RELEASE_SET_CONTRIBUTION,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
        payload=contribution,
    )

    graph = ClaimGraph()
    graph.add(release_set_claim)
    graph.add(artist_claim)
    graph.add_relationship(association_claim)

    _, association_resolutions_by_claim, _ = resolve_claim_graph(graph, keys_by_claim={})
    association_resolution = association_resolutions_by_claim.get(association_claim.claim_id)

    assert association_resolution is not None
    assert association_resolution.status is ResolutionStatus.RESOLVED
    assert association_resolution.target is contribution


def test_resolve_claim_graph_marks_association_blocked_for_ambiguous_endpoint() -> None:
    source_claim = EntityClaim(
        entity=ReleaseSet(title="Source"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    target_claim = EntityClaim(
        entity=Artist(name="Target"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    association_claim = AssociationClaim(
        source_claim_id=source_claim.claim_id,
        target_claim_id=target_claim.claim_id,
        kind=AssociationKind.RELEASE_SET_CONTRIBUTION,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )

    graph = ClaimGraph()
    graph.add(source_claim)
    graph.add(target_claim)
    graph.add_relationship(association_claim)

    def _by_normalized_key(_claim: EntityClaim, key: tuple[object, ...]) -> tuple[ReleaseSet, ...]:
        if key == ("release_set:artist-title", None, "source"):
            return (ReleaseSet(title="A"), ReleaseSet(title="B"))
        return ()

    keys_by_claim: KeysByClaim = {
        source_claim.claim_id: (("release_set:artist-title", None, "source"),),
    }
    _, association_resolutions_by_claim, _ = resolve_claim_graph(
        graph,
        keys_by_claim=keys_by_claim,
        find_by_normalized_key=_by_normalized_key,
    )
    association_resolution = association_resolutions_by_claim.get(association_claim.claim_id)

    assert association_resolution is not None
    assert association_resolution.status is ResolutionStatus.BLOCKED
    assert association_resolution.blocked_by_claim_ids == (source_claim.claim_id,)


def test_resolve_claim_graph_marks_link_resolved_without_target_payload() -> None:
    release_set = ReleaseSet(title="Mezzanine")
    release = release_set.create_release(title="Mezzanine")
    label = Label(name="Virgin")
    release.add_label(label)

    release_claim = EntityClaim(
        entity=release,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    label_claim = EntityClaim(
        entity=label,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    link_claim = LinkClaim(
        source_claim_id=release_claim.claim_id,
        target_claim_id=label_claim.claim_id,
        kind=LinkKind.RELEASE_LABEL,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )

    graph = ClaimGraph()
    graph.add(release_claim)
    graph.add(label_claim)
    graph.add_relationship(link_claim)

    _, _, link_resolutions_by_claim = resolve_claim_graph(graph, keys_by_claim={})
    link_resolution = link_resolutions_by_claim.get(link_claim.claim_id)

    assert isinstance(link_resolution, LinkResolvedResolution)
