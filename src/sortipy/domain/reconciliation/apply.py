"""Domain mutation contracts for reconciliation instructions.

Responsibilities of this stage:
- execute policy instructions via domain commands
- mutate canonical entities in memory
- avoid direct commit/transaction control

The implementation should keep all ORM-specific behavior out of this module.
Any session re-attachment/hydration concerns belong to persistence adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    AssociationKind,
    LinkKind,
    expect_association_payload,
    expect_relationship_entity,
)
from .contracts import (
    CreateInstruction,
    LinkCreateInstruction,
    LinkManualReviewInstruction,
    LinkNoopInstruction,
    ManualReviewInstruction,
    ManualReviewItem,
    ManualReviewSubject,
    MergeInstruction,
    NoopInstruction,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sortipy.domain.model import (
        AssociationEntity,
        ExternallyIdentifiable,
        IdentifiedEntity,
        Provenanced,
        ProvenanceTracked,
    )

    from .claims import (
        AssociationClaim,
        EntityClaim,
        LinkClaim,
    )
    from .contracts import (
        AssociationApplyInstruction,
        AssociationInstructionsByClaim,
        EntityApplyInstruction,
        EntityInstructionsByClaim,
        LinkApplyInstruction,
        LinkInstructionsByClaim,
    )
    from .graph import ClaimGraph


@dataclass(slots=True)
class ApplyCounters:
    """Outcome counters for one claim category."""

    created: int = 0
    merged: int = 0
    skipped: int = 0
    manual_review: int = 0

    @property
    def applied(self) -> int:
        return self.created + self.merged + self.skipped + self.manual_review


def _new_manual_review_items() -> list[ManualReviewItem]:
    return []


def _new_entities_by_claim() -> dict[UUID, IdentifiedEntity]:
    return {}


def _new_associations_by_claim() -> dict[UUID, AssociationEntity]:
    return {}


@dataclass(slots=True)
class ApplyResult:
    """Summary of in-memory mutations performed by the applier."""

    entities: ApplyCounters = field(default_factory=ApplyCounters)
    associations: ApplyCounters = field(default_factory=ApplyCounters)
    links: ApplyCounters = field(default_factory=ApplyCounters)
    manual_review_items: list[ManualReviewItem] = field(default_factory=_new_manual_review_items)
    entities_by_claim: dict[UUID, IdentifiedEntity] = field(default_factory=_new_entities_by_claim)
    associations_by_claim: dict[UUID, AssociationEntity] = field(
        default_factory=_new_associations_by_claim
    )


class ApplyReconciliationInstructions(Protocol):
    """Apply policy instructions to canonical domain entities."""

    def __call__(
        self,
        graph: ClaimGraph,
        *,
        entity_instructions_by_claim: EntityInstructionsByClaim,
        association_instructions_by_claim: AssociationInstructionsByClaim,
        link_instructions_by_claim: LinkInstructionsByClaim,
    ) -> ApplyResult: ...


def apply_reconciliation_instructions(
    graph: ClaimGraph,
    *,
    entity_instructions_by_claim: EntityInstructionsByClaim,
    association_instructions_by_claim: AssociationInstructionsByClaim,
    link_instructions_by_claim: LinkInstructionsByClaim,
) -> ApplyResult:
    """Apply policy instructions to claim entities in ``graph``.

    Entity merge semantics:
    - ``CREATE``: keep claim entity as materialized output candidate
    - ``MERGE``: merge incoming claim entity fields into resolved canonical target
    - ``NOOP``: no mutation
    - ``MANUAL_REVIEW``: no mutation
    """

    result = ApplyResult()
    entities_by_claim: dict[UUID, IdentifiedEntity] = {}

    for claim_id, instruction in entity_instructions_by_claim.items():
        claim = graph.require_claim(claim_id)
        materialized = _apply_entity_instruction(claim, instruction, result=result)
        if materialized is not None:
            entities_by_claim[claim_id] = materialized
            result.entities_by_claim[claim_id] = materialized

    for claim_id, instruction in association_instructions_by_claim.items():
        association = graph.require_association(claim_id)
        _apply_association_instruction(
            association,
            instruction,
            entities_by_claim=entities_by_claim,
            result=result,
        )

    for claim_id, instruction in link_instructions_by_claim.items():
        link = graph.require_link(claim_id)
        _apply_link_instruction(
            link,
            instruction,
            entities_by_claim=entities_by_claim,
            result=result,
        )

    _prune_superseded_entities(
        graph,
        entity_instructions_by_claim=entity_instructions_by_claim,
    )

    return result


def _apply_entity_instruction(
    claim: EntityClaim,
    instruction: EntityApplyInstruction,
    *,
    result: ApplyResult,
) -> IdentifiedEntity | None:
    match instruction:
        case CreateInstruction():
            result.entities.created += 1
            return claim.entity
        case MergeInstruction():
            _merge_entity_claim_into_target(
                claim,
                target=instruction.target,
            )
            result.entities.merged += 1
            return instruction.target
        case NoopInstruction():
            result.entities.skipped += 1
            return instruction.target if instruction.target is not None else claim.entity
        case ManualReviewInstruction():
            result.entities.manual_review += 1
            result.manual_review_items.append(
                ManualReviewItem(
                    claim_id=claim.claim_id,
                    subject=ManualReviewSubject.ENTITY,
                    kind=claim.entity_type,
                    blocked_by_claim_ids=instruction.blocked_by_claim_ids,
                    candidate_entity_ids=instruction.candidate_entity_ids,
                    reason=instruction.reason,
                )
            )
            return None


def _apply_association_instruction(
    association: AssociationClaim,
    instruction: AssociationApplyInstruction,
    *,
    entities_by_claim: dict[UUID, IdentifiedEntity],
    result: ApplyResult,
) -> None:
    match instruction:
        case CreateInstruction():
            created = _create_association(association, entities_by_claim=entities_by_claim)
            result.associations.created += 1
            if created is not None:
                result.associations_by_claim[association.claim_id] = created
        case MergeInstruction():
            _merge_association(
                association,
                target=instruction.target,
            )
            result.associations.merged += 1
            result.associations_by_claim[association.claim_id] = instruction.target
        case NoopInstruction():
            result.associations.skipped += 1
            if instruction.target is not None:
                result.associations_by_claim[association.claim_id] = instruction.target
        case ManualReviewInstruction():
            result.associations.manual_review += 1
            result.manual_review_items.append(
                ManualReviewItem(
                    claim_id=association.claim_id,
                    subject=ManualReviewSubject.ASSOCIATION,
                    kind=association.kind,
                    blocked_by_claim_ids=instruction.blocked_by_claim_ids,
                    candidate_entity_ids=instruction.candidate_entity_ids,
                    reason=instruction.reason,
                )
            )


def _apply_link_instruction(
    link: LinkClaim,
    instruction: LinkApplyInstruction,
    *,
    entities_by_claim: dict[UUID, IdentifiedEntity],
    result: ApplyResult,
) -> None:
    match instruction:
        case LinkCreateInstruction():
            _create_link(link, entities_by_claim=entities_by_claim)
            result.links.created += 1
        case LinkNoopInstruction():
            result.links.skipped += 1
        case LinkManualReviewInstruction():
            result.links.manual_review += 1
            result.manual_review_items.append(
                ManualReviewItem(
                    claim_id=link.claim_id,
                    subject=ManualReviewSubject.LINK,
                    kind=link.kind,
                    blocked_by_claim_ids=instruction.blocked_by_claim_ids,
                    candidate_entity_ids=instruction.candidate_entity_ids,
                    reason=instruction.reason,
                )
            )


def _merge_entity_claim_into_target(claim: EntityClaim, *, target: IdentifiedEntity) -> None:
    incoming = claim.entity
    if incoming.entity_type is not target.entity_type:
        msg = (
            f"Merge target type mismatch for claim {claim.claim_id}: "
            f"{incoming.entity_type} != {target.entity_type}"
        )
        raise ValueError(msg)

    match (incoming, target):
        case (Artist(), Artist()):
            _merge_artist(incoming, target)
        case (ReleaseSet(), ReleaseSet()):
            _merge_release_set(incoming, target)
        case (Release(), Release()):
            _merge_release(incoming, target)
        case (Recording(), Recording()):
            _merge_recording(incoming, target)
        case (Label(), Label()):
            _merge_label(incoming, target)
        case (User(), User()):
            _merge_user(incoming, target)
        case (LibraryItem(), LibraryItem()):
            _merge_library_item(incoming, target)
        case (PlayEvent(), PlayEvent()):
            _merge_play_event(incoming, target)
        case _:
            msg = (
                f"Unsupported merge entity type for claim {claim.claim_id}: "
                f"{type(incoming).__name__} -> {type(target).__name__}"
            )
            raise TypeError(msg)


def _merge_artist(incoming: Artist, target: Artist) -> None:
    target.name = _prefer_non_empty_string(incoming.name, target.name)
    target.sort_name = _prefer_optional_string(incoming.sort_name, target.sort_name)
    target.country = _prefer_optional_value(incoming.country, target.country)
    target.kind = _prefer_optional_value(incoming.kind, target.kind)
    target.life_span = _prefer_optional_value(incoming.life_span, target.life_span)
    target.formed_year = _prefer_optional_value(incoming.formed_year, target.formed_year)
    target.disbanded_year = _prefer_optional_value(incoming.disbanded_year, target.disbanded_year)
    _merge_unique_list(target.areas, incoming.areas)
    _merge_unique_list(target.aliases, incoming.aliases)
    _merge_external_ids(incoming, target)
    _merge_sources(incoming, target)


def _merge_release_set(incoming: ReleaseSet, target: ReleaseSet) -> None:
    target.title = _prefer_non_empty_string(incoming.title, target.title)
    target.primary_type = _prefer_optional_value(incoming.primary_type, target.primary_type)
    target.first_release = _prefer_optional_value(incoming.first_release, target.first_release)
    _merge_unique_list(target.secondary_types, incoming.secondary_types)
    _merge_unique_list(target.aliases, incoming.aliases)
    _merge_external_ids(incoming, target)
    _merge_sources(incoming, target)


def _merge_release(incoming: Release, target: Release) -> None:
    target.title = _prefer_non_empty_string(incoming.title, target.title)
    target.release_date = _prefer_optional_value(incoming.release_date, target.release_date)
    target.country = _prefer_optional_value(incoming.country, target.country)
    target.status = _prefer_optional_value(incoming.status, target.status)
    target.packaging = _prefer_optional_value(incoming.packaging, target.packaging)
    target.format = _prefer_optional_string(incoming.format, target.format)
    target.medium_count = _prefer_optional_value(incoming.medium_count, target.medium_count)
    _merge_external_ids(incoming, target)
    _merge_sources(incoming, target)


def _merge_recording(incoming: Recording, target: Recording) -> None:
    target.title = _prefer_non_empty_string(incoming.title, target.title)
    target.duration_ms = _prefer_optional_value(incoming.duration_ms, target.duration_ms)
    target.version = _prefer_optional_string(incoming.version, target.version)
    target.disambiguation = _prefer_optional_string(incoming.disambiguation, target.disambiguation)
    _merge_unique_list(target.aliases, incoming.aliases)
    _merge_external_ids(incoming, target)
    _merge_sources(incoming, target)


def _merge_label(incoming: Label, target: Label) -> None:
    target.name = _prefer_non_empty_string(incoming.name, target.name)
    target.country = _prefer_optional_value(incoming.country, target.country)
    _merge_external_ids(incoming, target)
    _merge_sources(incoming, target)


def _merge_user(incoming: User, target: User) -> None:
    target.display_name = _prefer_non_empty_string(incoming.display_name, target.display_name)
    target.email = _prefer_optional_string(incoming.email, target.email)
    target.spotify_user_id = _prefer_optional_string(
        incoming.spotify_user_id,
        target.spotify_user_id,
    )
    target.lastfm_user = _prefer_optional_string(incoming.lastfm_user, target.lastfm_user)
    _merge_sources(incoming, target)


def _merge_library_item(incoming: LibraryItem, target: LibraryItem) -> None:
    target.source = _prefer_optional_value(incoming.source, target.source)
    target.saved_at = _prefer_optional_value(incoming.saved_at, target.saved_at)
    _merge_sources(incoming, target)


def _merge_play_event(incoming: PlayEvent, target: PlayEvent) -> None:
    target.duration_ms = _prefer_optional_value(incoming.duration_ms, target.duration_ms)
    _merge_sources(incoming, target)


def _prefer_non_empty_string(incoming: str, fallback: str) -> str:
    return incoming if incoming.strip() else fallback


def _prefer_optional_string(incoming: str | None, fallback: str | None) -> str | None:
    if incoming is None or not incoming.strip():
        return fallback
    return incoming


def _prefer_optional_value[TValue](
    incoming: TValue | None,
    fallback: TValue | None,
) -> TValue | None:
    return incoming if incoming is not None else fallback


def _merge_unique_list[TItem](target: list[TItem], incoming: list[TItem]) -> None:
    for item in incoming:
        if item not in target:
            target.append(item)


def _merge_sources(source_entity: Provenanced, target_entity: ProvenanceTracked) -> None:
    source_provenance = source_entity.provenance
    if source_provenance is None:
        return
    for source in source_provenance.sources:
        target_entity.add_source(source)


def _merge_external_ids(
    source_entity: ExternallyIdentifiable,
    target_entity: ExternallyIdentifiable,
) -> None:
    source_external_ids = source_entity.external_ids
    target_external_ids = target_entity.external_ids
    existing = {(external_id.namespace, external_id.value) for external_id in target_external_ids}
    for external_id in source_external_ids:
        key = (external_id.namespace, external_id.value)
        if key in existing:
            continue
        target_entity.add_external_id(
            external_id.namespace,
            external_id.value,
            provider=external_id.provider,
        )
        existing.add(key)


def _create_association(
    association: AssociationClaim,
    *,
    entities_by_claim: dict[UUID, IdentifiedEntity],
) -> AssociationEntity | None:
    source = _entity_for_relationship_endpoint(
        association.source_claim_id,
        entities_by_claim=entities_by_claim,
        endpoint="source",
        relationship=association,
    )
    target = _entity_for_relationship_endpoint(
        association.target_claim_id,
        entities_by_claim=entities_by_claim,
        endpoint="target",
        relationship=association,
    )

    match association.kind:
        case AssociationKind.RELEASE_SET_CONTRIBUTION:
            return _create_release_set_contribution(association, source=source, target=target)
        case AssociationKind.RECORDING_CONTRIBUTION:
            return _create_recording_contribution(association, source=source, target=target)
        case AssociationKind.RELEASE_TRACK:
            return _create_release_track(association, source=source, target=target)
        case _:
            raise ValueError(f"Unsupported association kind: {association.kind}")


def _merge_association(
    association: AssociationClaim,
    *,
    target: AssociationEntity,
) -> None:
    payload = association.payload
    if payload is None:
        msg = f"Association {association.claim_id} merge requires payload, but payload is missing"
        raise ValueError(msg)

    match (payload, target):
        case (ReleaseSetContribution(), ReleaseSetContribution()):
            _merge_release_set_contribution(payload, target=target)
        case (RecordingContribution(), RecordingContribution()):
            _merge_recording_contribution(payload, target=target)
        case (ReleaseTrack(), ReleaseTrack()):
            _merge_release_track(payload, target=target)
        case _:
            msg = (
                f"Association {association.claim_id} merge target type mismatch: "
                f"{type(payload).__name__} -> {type(target).__name__}"
            )
            raise TypeError(msg)


def _create_link(
    link: LinkClaim,
    *,
    entities_by_claim: dict[UUID, IdentifiedEntity],
) -> None:
    source = _entity_for_relationship_endpoint(
        link.source_claim_id,
        entities_by_claim=entities_by_claim,
        endpoint="source",
        relationship=link,
    )
    target = _entity_for_relationship_endpoint(
        link.target_claim_id,
        entities_by_claim=entities_by_claim,
        endpoint="target",
        relationship=link,
    )

    match link.kind:
        case LinkKind.RELEASE_LABEL:
            release = expect_relationship_entity(source, Release, relationship_claim=link)
            label = expect_relationship_entity(target, Label, relationship_claim=link)
            release.add_label(label)
        case LinkKind.RELEASE_SET_RELEASE:
            release_set = expect_relationship_entity(source, ReleaseSet, relationship_claim=link)
            release = expect_relationship_entity(target, Release, relationship_claim=link)
            release_set.add_release(release)
        case LinkKind.USER_LIBRARY_ITEM:
            user = expect_relationship_entity(source, User, relationship_claim=link)
            library_item = expect_relationship_entity(
                target,
                LibraryItem,
                relationship_claim=link,
            )
            user.rehydrate_library_item(library_item)
        case LinkKind.USER_PLAY_EVENT:
            user = expect_relationship_entity(source, User, relationship_claim=link)
            play_event = expect_relationship_entity(target, PlayEvent, relationship_claim=link)
            user.rehydrate_play_event(play_event)
        case _:
            raise ValueError(f"Unsupported link kind: {link.kind}")


def _create_release_set_contribution(
    association: AssociationClaim,
    *,
    source: IdentifiedEntity,
    target: IdentifiedEntity,
) -> ReleaseSetContribution:
    release_set = expect_relationship_entity(source, ReleaseSet, relationship_claim=association)
    artist = expect_relationship_entity(target, Artist, relationship_claim=association)
    payload = association.payload
    if payload is None:
        return release_set.add_artist(artist)
    contribution = expect_association_payload(
        payload,
        ReleaseSetContribution,
        relationship_claim=association,
    )
    return release_set.adopt_contribution(contribution, artist=artist)


def _create_recording_contribution(
    association: AssociationClaim,
    *,
    source: IdentifiedEntity,
    target: IdentifiedEntity,
) -> RecordingContribution:
    recording = expect_relationship_entity(source, Recording, relationship_claim=association)
    artist = expect_relationship_entity(target, Artist, relationship_claim=association)
    payload = association.payload
    if payload is None:
        return recording.add_artist(artist)
    contribution = expect_association_payload(
        payload,
        RecordingContribution,
        relationship_claim=association,
    )
    return recording.adopt_contribution(contribution, artist=artist)


def _create_release_track(
    association: AssociationClaim,
    *,
    source: IdentifiedEntity,
    target: IdentifiedEntity,
) -> ReleaseTrack:
    release = expect_relationship_entity(source, Release, relationship_claim=association)
    recording = expect_relationship_entity(target, Recording, relationship_claim=association)
    payload = association.payload
    if payload is None:
        return release.add_track(recording)
    track = expect_association_payload(
        payload,
        ReleaseTrack,
        relationship_claim=association,
    )
    return release.adopt_track(track, recording=recording)


def _merge_release_set_contribution(
    payload: ReleaseSetContribution,
    *,
    target: ReleaseSetContribution,
) -> None:
    target.role = payload.role
    target.credit_order = payload.credit_order
    target.credited_as = payload.credited_as
    target.join_phrase = payload.join_phrase
    _merge_sources(payload, target)


def _merge_recording_contribution(
    payload: RecordingContribution,
    *,
    target: RecordingContribution,
) -> None:
    target.role = payload.role
    target.credit_order = payload.credit_order
    target.credited_as = payload.credited_as
    target.join_phrase = payload.join_phrase
    _merge_sources(payload, target)


def _merge_release_track(
    payload: ReleaseTrack,
    *,
    target: ReleaseTrack,
) -> None:
    target.disc_number = payload.disc_number
    target.track_number = payload.track_number
    target.title_override = payload.title_override
    target.duration_ms = payload.duration_ms
    _merge_external_ids(payload, target)
    _merge_sources(payload, target)


def _prune_superseded_entities(
    graph: ClaimGraph,
    *,
    entity_instructions_by_claim: EntityInstructionsByClaim,
) -> None:
    for claim_id, instruction in entity_instructions_by_claim.items():
        claim = graph.require_claim(claim_id)
        match (claim.entity, instruction):
            case (Release() as release, MergeInstruction(target=target)) if target is not release:
                release.release_set.remove_release(release)
            case (Release() as release, NoopInstruction(target=target)) if (
                target is not None and target is not release
            ):
                release.release_set.remove_release(release)
            case _:
                pass


def _entity_for_relationship_endpoint(
    claim_id: UUID,
    *,
    entities_by_claim: dict[UUID, IdentifiedEntity],
    endpoint: str,
    relationship: AssociationClaim | LinkClaim,
) -> IdentifiedEntity:
    entity = entities_by_claim.get(claim_id)
    if entity is None:
        msg = (
            f"Missing {endpoint} endpoint entity for relationship claim {relationship.claim_id}: "
            f"{claim_id}"
        )
        raise ValueError(msg)
    return entity
