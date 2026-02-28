"""Canonical identity resolution contracts.

Responsibilities of this stage:
- resolve claim representatives against canonical entities from repositories
- classify each entity claim as NEW/RESOLVED/AMBIGUOUS/CONFLICT
- classify each association/link claim without mutating persistence state

TODO:
- consume richer key evidence directly from normalization output so resolver
  implementations can combine exact lookup and fuzzy matching without
  recomputing normalization.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from sortipy.domain.model import (
    Artist,
    Label,
    LibraryItem,
    PlayEvent,
    Recording,
    RecordingContribution,
    Release,
    ReleaseSet,
    ReleaseSetContribution,
    ReleaseTrack,
    User,
)

from .claims import (
    AssociationClaim,
    AssociationKind,
    ClaimEntity,
    LinkKind,
)
from .contracts import (
    AmbiguousResolution,
    BlockedResolution,
    ConflictResolution,
    LinkConflictResolution,
    LinkResolvedResolution,
    MatchKind,
    NewResolution,
    ResolvedResolution,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sortipy.domain.model import Namespace

    from .claims import AssociationEntity, EntityClaim, LinkClaim, RelationshipClaimEntity
    from .contracts import (
        AssociationResolution,
        AssociationResolutionsByClaim,
        ClaimKey,
        EntityResolution,
        EntityResolutionsByClaim,
        KeysByClaim,
        LinkResolution,
        LinkResolutionsByClaim,
    )
    from .graph import ClaimGraph


class ResolveClaimGraph(Protocol):
    """Resolve claims against canonical catalog state."""

    def __call__(
        self,
        graph: ClaimGraph,
        *,
        keys_by_claim: KeysByClaim,
    ) -> tuple[EntityResolutionsByClaim, AssociationResolutionsByClaim, LinkResolutionsByClaim]: ...


type FindByExternalId = Callable[[EntityClaim, Namespace, str], tuple[ClaimEntity, ...]]
type FindByNormalizedKey = Callable[[EntityClaim, ClaimKey], tuple[ClaimEntity, ...]]


class ResolveError(Exception):
    """Base exception for resolver-internal control flow and validation failures."""

    reason: str
    context: dict[str, object]

    def __init__(
        self,
        reason: str,
        *,
        message: str | None = None,
        context: dict[str, object] | None = None,
    ) -> None:
        self.reason = reason
        self.context = {} if context is None else context
        super().__init__(reason if message is None else message)


class RelationshipTypeError(ResolveError):
    """Raised when relationship endpoints/payload do not match relationship kind."""

    def __init__(
        self,
        reason: str,
        *,
        endpoint: str | None = None,
        expected: str | None = None,
        actual: str | None = None,
    ) -> None:
        context: dict[str, object] = {}
        if endpoint is not None:
            context["endpoint"] = endpoint
        if expected is not None:
            context["expected"] = expected
        if actual is not None:
            context["actual"] = actual
        super().__init__(reason, context=context)


class MissingEndpointResolutionError(ResolveError):
    """Raised when relationship endpoints are unresolved in entity resolution output."""

    unresolved_claim_ids: tuple[UUID, ...]

    def __init__(
        self,
        *,
        unresolved_claim_ids: tuple[UUID, ...],
    ) -> None:
        if not unresolved_claim_ids:
            msg = "MissingEndpointResolutionError requires at least one unresolved claim ID."
            raise ValueError(msg)
        self.unresolved_claim_ids = unresolved_claim_ids
        super().__init__(
            "relationship_endpoint_unresolved",
            context={
                "unresolved_claim_ids": tuple(str(claim_id) for claim_id in unresolved_claim_ids),
            },
        )


def resolve_claim_graph(
    graph: ClaimGraph,
    *,
    keys_by_claim: KeysByClaim,
    find_by_external_id: FindByExternalId | None = None,
    find_by_normalized_key: FindByNormalizedKey | None = None,
) -> tuple[EntityResolutionsByClaim, AssociationResolutionsByClaim, LinkResolutionsByClaim]:
    """Resolve entities and relationship claims against canonical state."""

    entity_resolutions_by_claim: EntityResolutionsByClaim = {}
    for claim in graph.claims:
        keys = keys_by_claim.get(claim.claim_id, ())
        candidates, matched_key = _find_exact_candidates_for_claim(
            claim,
            keys,
            find_by_external_id=find_by_external_id,
            find_by_normalized_key=find_by_normalized_key,
        )
        entity_resolutions_by_claim[claim.claim_id] = _resolution_for_claim(
            claim,
            candidates=_dedupe_candidates(candidates),
            matched_key=matched_key,
        )

    association_resolutions_by_claim: AssociationResolutionsByClaim = {}
    link_resolutions_by_claim: LinkResolutionsByClaim = {}
    for relationship in graph.relationships:
        if isinstance(relationship, AssociationClaim):
            association_resolutions_by_claim[relationship.claim_id] = (
                _association_resolution_for_claim(
                    relationship,
                    graph=graph,
                    entity_resolutions_by_claim=entity_resolutions_by_claim,
                )
            )
            continue
        link_resolutions_by_claim[relationship.claim_id] = _link_resolution_for_claim(
            relationship,
            graph=graph,
            entity_resolutions_by_claim=entity_resolutions_by_claim,
        )

    return (
        entity_resolutions_by_claim,
        association_resolutions_by_claim,
        link_resolutions_by_claim,
    )


def _resolution_for_claim(
    claim: EntityClaim,
    *,
    candidates: tuple[ClaimEntity, ...],
    matched_key: ClaimKey | None,
) -> EntityResolution:
    if any(candidate.entity_type is not claim.entity_type for candidate in candidates):
        return ConflictResolution(
            candidates=candidates,
            matched_key=matched_key,
            match_kind=MatchKind.EXACT,
            reason="candidate_type_mismatch",
        )

    if not candidates:
        return NewResolution(reason="no_exact_match")

    if len(candidates) == 1:
        return ResolvedResolution(
            target=candidates[0],
            matched_key=matched_key,
            match_kind=MatchKind.EXACT,
            reason="exact_match",
        )

    return AmbiguousResolution(
        candidates=candidates,
        matched_key=matched_key,
        match_kind=MatchKind.EXACT,
        reason="multiple_exact_matches",
    )


def _association_resolution_for_claim(
    relationship: AssociationClaim,
    *,
    graph: ClaimGraph,
    entity_resolutions_by_claim: EntityResolutionsByClaim,
) -> AssociationResolution:
    try:
        source, target = _resolved_relationship_endpoints(
            relationship.source_claim_id,
            relationship.target_claim_id,
            graph=graph,
            entity_resolutions_by_claim=entity_resolutions_by_claim,
        )
    except MissingEndpointResolutionError as e:
        return BlockedResolution(
            blocked_by_claim_ids=e.unresolved_claim_ids,
            reason=e.reason,
        )

    try:
        candidates = _association_candidates_for_kind(
            relationship.kind,
            source,
            target,
            relationship.payload,
            relationship_claim_id=relationship.claim_id,
        )
    except RelationshipTypeError as e:
        return ConflictResolution(reason=e.reason)

    if not candidates:
        return NewResolution(reason="association_not_found")
    if len(candidates) == 1:
        return ResolvedResolution(target=candidates[0], reason="association_found")
    return AmbiguousResolution(candidates=candidates, reason="multiple_association_matches")


def _association_candidates_for_kind(
    association_kind: AssociationKind,
    source: ClaimEntity,
    target: ClaimEntity,
    payload: RelationshipClaimEntity | None,
    *,
    relationship_claim_id: UUID,
) -> tuple[AssociationEntity, ...]:
    match association_kind:
        case AssociationKind.RELEASE_TRACK:
            release, recording, _track = _validate_association_types(
                types=(Release, Recording, ReleaseTrack),
                entities=(source, target, payload),
            )
            return tuple(
                track
                for track in release.tracks
                if track.recording.resolved_id == recording.resolved_id
            )

        case AssociationKind.RELEASE_SET_CONTRIBUTION:
            release_set, artist, _contribution = _validate_association_types(
                types=(ReleaseSet, Artist, ReleaseSetContribution),
                entities=(source, target, payload),
            )
            return tuple(
                contribution
                for contribution in release_set.contributions
                if contribution.artist.resolved_id == artist.resolved_id
            )

        case AssociationKind.RECORDING_CONTRIBUTION:
            recording, artist, _contribution = _validate_association_types(
                types=(Recording, Artist, RecordingContribution),
                entities=(source, target, payload),
            )
            return tuple(
                contribution
                for contribution in recording.contributions
                if contribution.artist.resolved_id == artist.resolved_id
            )
        case _:
            raise RelationshipTypeError(
                "unsupported_association_kind",
                relationship_claim_id=relationship_claim_id,
                relationship_kind=association_kind,
                endpoint="kind",
                actual=association_kind.value,
            )


def _validate_association_types[TS: ClaimEntity, TT: ClaimEntity, TP: RelationshipClaimEntity](
    *,
    types: tuple[type[TS], type[TT], type[TP]],
    entities: tuple[ClaimEntity, ClaimEntity, RelationshipClaimEntity | None],
) -> tuple[TS, TT, TP | None]:
    source_type, target_type, payload_type = types
    source, target, payload = entities
    if not isinstance(source, source_type):
        raise RelationshipTypeError(
            "relationship_source_type_mismatch",
            endpoint="source",
            expected=source_type.__name__,
            actual=type(source).__name__,
        )
    if not isinstance(target, target_type):
        raise RelationshipTypeError(
            "relationship_target_type_mismatch",
            endpoint="target",
            expected=target_type.__name__,
            actual=type(target).__name__,
        )
    if payload is not None and not isinstance(payload, payload_type):
        raise RelationshipTypeError(
            "invalid_relationship_payload",
            endpoint="payload",
            expected=payload_type.__name__,
            actual=type(payload).__name__,
        )
    return source, target, payload


def _link_resolution_for_claim(
    relationship: LinkClaim,
    *,
    graph: ClaimGraph,
    entity_resolutions_by_claim: EntityResolutionsByClaim,
) -> LinkResolution:
    try:
        source, target = _resolved_relationship_endpoints(
            relationship.source_claim_id,
            relationship.target_claim_id,
            graph=graph,
            entity_resolutions_by_claim=entity_resolutions_by_claim,
        )
    except MissingEndpointResolutionError as e:
        return BlockedResolution(
            blocked_by_claim_ids=e.unresolved_claim_ids,
            reason=e.reason,
        )

    try:
        link_exists = _check_link_existence(
            relationship.kind,
            source,
            target,
            relationship_claim_id=relationship.claim_id,
        )
    except RelationshipTypeError as e:
        return LinkConflictResolution(reason=e.reason)

    if link_exists:
        return LinkResolvedResolution(reason="link_found")
    return NewResolution(reason="link_not_found")


def _validate_link_types[TS: ClaimEntity, TT: ClaimEntity](
    *,
    types: tuple[type[TS], type[TT]],
    entities: tuple[ClaimEntity, ClaimEntity],
) -> tuple[TS, TT]:
    source_type, target_type = types
    source, target = entities
    if not isinstance(source, source_type):
        raise RelationshipTypeError(
            "relationship_source_type_mismatch",
            endpoint="source",
            expected=source_type.__name__,
            actual=type(source).__name__,
        )
    if not isinstance(target, target_type):
        raise RelationshipTypeError(
            "relationship_target_type_mismatch",
            endpoint="target",
            expected=target_type.__name__,
            actual=type(target).__name__,
        )
    return source, target


def _check_link_existence(
    link_kind: LinkKind,
    source: ClaimEntity,
    target: ClaimEntity,
    *,
    relationship_claim_id: UUID,
) -> bool:
    match link_kind:
        case LinkKind.RELEASE_LABEL:
            release, label = _validate_link_types(types=(Release, Label), entities=(source, target))
            return any(lab.resolved_id == label.resolved_id for lab in release.labels)
        case LinkKind.RELEASE_SET_RELEASE:
            release_set, release = _validate_link_types(
                types=(ReleaseSet, Release), entities=(source, target)
            )
            return any(rel.resolved_id == release.resolved_id for rel in release_set.releases)
        case LinkKind.USER_LIBRARY_ITEM:
            user, library_item = _validate_link_types(
                types=(User, LibraryItem), entities=(source, target)
            )
            return any(item.id == library_item.id for item in user.library_items)
        case LinkKind.USER_PLAY_EVENT:
            user, play_event = _validate_link_types(
                types=(User, PlayEvent), entities=(source, target)
            )
            return any(event.id == play_event.id for event in user.play_events)
        case _:
            raise RelationshipTypeError(
                "unsupported_link_kind",
                relationship_claim_id=relationship_claim_id,
                relationship_kind=link_kind,
                endpoint="kind",
                actual=link_kind.value,
            )


def _resolved_relationship_endpoints(
    source_claim_id: UUID,
    target_claim_id: UUID,
    *,
    graph: ClaimGraph,
    entity_resolutions_by_claim: EntityResolutionsByClaim,
) -> tuple[ClaimEntity, ClaimEntity]:
    unresolved_claim_ids: list[UUID] = []

    source = _resolved_endpoint_entity_or_none(
        source_claim_id,
        graph=graph,
        entity_resolutions_by_claim=entity_resolutions_by_claim,
    )
    if source is None:
        unresolved_claim_ids.append(source_claim_id)

    target = _resolved_endpoint_entity_or_none(
        target_claim_id,
        graph=graph,
        entity_resolutions_by_claim=entity_resolutions_by_claim,
    )
    if target is None:
        unresolved_claim_ids.append(target_claim_id)

    if unresolved_claim_ids:
        raise MissingEndpointResolutionError(
            unresolved_claim_ids=tuple(dict.fromkeys(unresolved_claim_ids))
        )
    if source is None or target is None:
        raise MissingEndpointResolutionError(
            unresolved_claim_ids=tuple(dict.fromkeys((source_claim_id, target_claim_id)))
        )
    return source, target


def _resolved_endpoint_entity_or_none(
    claim_id: UUID,
    *,
    graph: ClaimGraph,
    entity_resolutions_by_claim: EntityResolutionsByClaim,
) -> ClaimEntity | None:
    resolution = entity_resolutions_by_claim.get(claim_id)
    if resolution is None or isinstance(
        resolution, (AmbiguousResolution, ConflictResolution, BlockedResolution)
    ):
        return None
    if isinstance(resolution, ResolvedResolution):
        return resolution.target
    claim = graph.claim_for(claim_id)
    return claim.entity if claim is not None else None


def _dedupe_candidates(
    candidates: tuple[ClaimEntity, ...],
) -> tuple[ClaimEntity, ...]:
    seen: set[tuple[object, object]] = set()
    deduped: list[ClaimEntity] = []
    for candidate in candidates:
        key = (candidate.entity_type, candidate.resolved_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return tuple(deduped)


def _find_exact_candidates_for_claim(
    claim: EntityClaim,
    keys: tuple[ClaimKey, ...],
    *,
    find_by_external_id: FindByExternalId | None,
    find_by_normalized_key: FindByNormalizedKey | None,
) -> tuple[tuple[ClaimEntity, ...], ClaimKey | None]:
    external_lookup = _match_from_external_ids(claim, find_by_external_id=find_by_external_id)
    if external_lookup is not None:
        return external_lookup

    key_lookup = _match_from_keys(
        claim,
        keys,
        find_by_normalized_key=find_by_normalized_key,
    )
    if key_lookup is not None:
        return key_lookup

    return (), None


def _match_from_external_ids(
    claim: EntityClaim,
    *,
    find_by_external_id: FindByExternalId | None,
) -> tuple[tuple[ClaimEntity, ...], ClaimKey] | None:
    if find_by_external_id is None:
        return None
    if not hasattr(claim.entity, "external_ids"):
        return None

    external_ids = getattr(claim.entity, "external_ids", ())
    for external_id in external_ids:
        candidates = find_by_external_id(claim, external_id.namespace, external_id.value)
        if candidates:
            return candidates, ("external_id", external_id.namespace, external_id.value)
    return None


def _match_from_keys(
    claim: EntityClaim,
    keys: tuple[ClaimKey, ...],
    *,
    find_by_normalized_key: FindByNormalizedKey | None,
) -> tuple[tuple[ClaimEntity, ...], ClaimKey] | None:
    if find_by_normalized_key is None:
        return None

    all_candidates: list[ClaimEntity] = []
    matched_key: ClaimKey | None = None
    for key in keys:
        candidates = find_by_normalized_key(claim, key)
        if not candidates:
            continue
        if matched_key is None:
            matched_key = key
        all_candidates.extend(candidates)
    if not all_candidates or matched_key is None:
        return None
    return tuple(all_candidates), matched_key
