"""Persistence contracts and implementation for reconciliation output.

Responsibilities of this stage:
- persist newly created canonical/user entities
- persist normalization sidecars for resolved claims
- commit transaction boundaries on the provided unit of work
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, cast

from sortipy.domain.model import (
    Artist,
    Entity,
    Label,
    LibraryItem,
    PlayEvent,
    Recording,
    Release,
    ReleaseSet,
    User,
)
from sortipy.domain.ports.unit_of_work import RepositoryCollection, UnitOfWork

from .claims import AssociationClaim
from .contracts import (
    CreateInstruction,
    ManualReviewInstruction,
    MergeInstruction,
    NoopInstruction,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from uuid import UUID

    from sortipy.domain.model import (
        IdentifiedEntity,
    )
    from sortipy.domain.ports.persistence import (
        ArtistRepository,
        LabelRepository,
        LibraryItemRepository,
        MutationRepository,
        NormalizationSidecarRepository,
        PlayEventRepository,
        RecordingRepository,
        ReleaseRepository,
        ReleaseSetRepository,
        UserRepository,
    )

    from .apply import ApplyResult
    from .contracts import (
        AssociationInstructionsByClaim,
        ClaimKey,
        EntityApplyInstruction,
        EntityInstructionsByClaim,
        KeysByClaim,
        LinkInstructionsByClaim,
    )
    from .graph import ClaimGraph


class ReconciliationRepositories(RepositoryCollection, Protocol):
    """Repositories required for reconciliation persistence."""

    @property
    def artists(self) -> ArtistRepository: ...

    @property
    def labels(self) -> LabelRepository: ...

    @property
    def release_sets(self) -> ReleaseSetRepository: ...

    @property
    def releases(self) -> ReleaseRepository: ...

    @property
    def recordings(self) -> RecordingRepository: ...

    @property
    def users(self) -> UserRepository: ...

    @property
    def library_items(self) -> LibraryItemRepository: ...

    @property
    def play_events(self) -> PlayEventRepository: ...

    @property
    def normalization_sidecars(self) -> NormalizationSidecarRepository: ...

    @property
    def mutations(self) -> MutationRepository: ...


type ReconciliationUnitOfWork = UnitOfWork[ReconciliationRepositories]


@dataclass(slots=True)
class _PriorityKeysData:
    priority_keys: tuple[tuple[object, ...], ...]


@dataclass(slots=True)
class PersistenceResult:
    """Summary of persisted changes for one reconciliation run."""

    committed: bool
    persisted_entities: int = 0
    persisted_sidecars: int = 0
    persisted_events: int = 0


class PersistReconciliation(Protocol):
    """Persist applied reconciliation changes and commit transaction state."""

    def __call__(
        self,
        *,
        graph: ClaimGraph,
        keys_by_claim: KeysByClaim,
        entity_instructions_by_claim: EntityInstructionsByClaim,
        association_instructions_by_claim: AssociationInstructionsByClaim,
        link_instructions_by_claim: LinkInstructionsByClaim,
        apply_result: ApplyResult,
        uow: ReconciliationUnitOfWork,
    ) -> PersistenceResult: ...


def persist_reconciliation(
    *,
    graph: ClaimGraph,
    keys_by_claim: KeysByClaim,
    entity_instructions_by_claim: EntityInstructionsByClaim,
    association_instructions_by_claim: AssociationInstructionsByClaim,
    link_instructions_by_claim: LinkInstructionsByClaim,
    apply_result: ApplyResult,
    uow: ReconciliationUnitOfWork,
) -> PersistenceResult:
    """Persist reconciliation outcomes through repository ports and commit ``uow``."""
    _ = link_instructions_by_claim

    persisted_entities = 0
    persisted_sidecars = 0
    sidecar_targets: list[tuple[IdentifiedEntity, tuple[ClaimKey, ...]]] = []

    for claim_id in _sorted_entity_claim_ids(
        graph,
        entity_instructions_by_claim=entity_instructions_by_claim,
    ):
        claim = graph.require_claim(claim_id)
        instruction = entity_instructions_by_claim[claim_id]

        sidecar_target = _persist_entity_claim(
            claim.entity,
            instruction,
            repositories=uow.repositories,
        )
        if isinstance(instruction, CreateInstruction):
            persisted_entities += 1

        claim_keys = keys_by_claim.get(claim_id, ())
        if sidecar_target is None or not claim_keys:
            continue
        sidecar_targets.append((sidecar_target, claim_keys))

    for sidecar_target, claim_keys in sidecar_targets:
        normalized_keys = _normalization_keys(claim_keys)
        existing_before = uow.repositories.normalization_sidecars.find_by_keys(
            sidecar_target.entity_type,
            normalized_keys,
        )
        keys_before = _keys_for_entity(existing_before, entity=sidecar_target)

        uow.repositories.normalization_sidecars.save(
            sidecar_target,
            _PriorityKeysData(priority_keys=normalized_keys),
        )
        existing_after = uow.repositories.normalization_sidecars.find_by_keys(
            sidecar_target.entity_type,
            normalized_keys,
        )
        keys_after = _keys_for_entity(existing_after, entity=sidecar_target)
        persisted_sidecars += len(keys_after - keys_before)

    for created_association in _created_association_targets(
        association_instructions_by_claim=association_instructions_by_claim,
        apply_result=apply_result,
    ):
        uow.repositories.mutations.attach_created(created_association)

    dirty_targets = _dirty_targets_for_update(
        entity_instructions_by_claim=entity_instructions_by_claim,
        association_instructions_by_claim=association_instructions_by_claim,
    )
    for dirty_target in dirty_targets:
        uow.repositories.mutations.update(
            dirty_target,
            changed_fields=dirty_target.changed_fields,
        )

    uow.commit()
    _clear_dirty_fields_after_commit(
        graph=graph,
        apply_result=apply_result,
        entity_instructions_by_claim=entity_instructions_by_claim,
        association_instructions_by_claim=association_instructions_by_claim,
    )
    return PersistenceResult(
        committed=True,
        persisted_entities=persisted_entities,
        persisted_sidecars=persisted_sidecars,
    )


def _sorted_entity_claim_ids(
    graph: ClaimGraph,
    *,
    entity_instructions_by_claim: EntityInstructionsByClaim,
) -> list[UUID]:
    ordered = sorted(
        entity_instructions_by_claim,
        key=lambda claim_id: (
            _persistence_priority(graph.require_claim(claim_id).entity),
            str(claim_id),
        ),
    )
    return list(ordered)


def _persistence_priority(entity: IdentifiedEntity) -> int:
    match entity:
        case User():
            priority = 0
        case Artist() | Label():
            priority = 1
        case ReleaseSet():
            priority = 2
        case Release():
            priority = 3
        case Recording():
            priority = 4
        case LibraryItem():
            priority = 5
        case PlayEvent():
            priority = 6
        case _:
            priority = 99
    return priority


def _persist_entity_claim(
    entity: IdentifiedEntity,
    instruction: EntityApplyInstruction,
    *,
    repositories: ReconciliationRepositories,
) -> IdentifiedEntity | None:
    match instruction:
        case CreateInstruction():
            _add_entity(entity, repositories=repositories)
            return entity
        case MergeInstruction():
            return instruction.target
        case NoopInstruction():
            return instruction.target
        case ManualReviewInstruction():
            return None


def _add_entity(entity: IdentifiedEntity, *, repositories: ReconciliationRepositories) -> None:
    match entity:
        case Artist():
            repositories.artists.add(entity)
        case Label():
            repositories.labels.add(entity)
        case ReleaseSet():
            repositories.release_sets.add(entity)
        case Release():
            repositories.releases.add(entity)
        case Recording():
            repositories.recordings.add(entity)
        case User():
            repositories.users.add(entity)
        case LibraryItem():
            repositories.library_items.add(entity)
        case PlayEvent():
            repositories.play_events.add(entity)
        case _:
            msg = f"Unsupported reconciliation persistence entity type: {type(entity).__name__}"
            raise TypeError(msg)


def _dirty_targets_for_update(
    *,
    entity_instructions_by_claim: EntityInstructionsByClaim,
    association_instructions_by_claim: AssociationInstructionsByClaim,
) -> tuple[Entity, ...]:
    ordered_targets: list[Entity] = []
    seen: set[int] = set()

    for instruction in entity_instructions_by_claim.values():
        match instruction:
            case MergeInstruction(target=target) | NoopInstruction(target=target):
                if not isinstance(target, Entity):
                    continue
                if not target.has_changes or id(target) in seen:
                    continue
                ordered_targets.append(target)
                seen.add(id(target))
            case _:
                continue

    for instruction in association_instructions_by_claim.values():
        match instruction:
            case MergeInstruction(target=target) | NoopInstruction(target=target):
                if not isinstance(target, Entity):
                    continue
                if not target.has_changes or id(target) in seen:
                    continue
                ordered_targets.append(target)
                seen.add(id(target))
            case _:
                continue

    return tuple(ordered_targets)


def _created_association_targets(
    *,
    association_instructions_by_claim: AssociationInstructionsByClaim,
    apply_result: ApplyResult,
) -> tuple[Entity, ...]:
    ordered_targets: list[Entity] = []
    seen: set[int] = set()

    for claim_id, instruction in association_instructions_by_claim.items():
        if not isinstance(instruction, CreateInstruction):
            continue
        created = apply_result.associations_by_claim.get(claim_id)
        if not isinstance(created, Entity):
            continue
        marker = id(created)
        if marker in seen:
            continue
        ordered_targets.append(created)
        seen.add(marker)

    return tuple(ordered_targets)


def _clear_dirty_fields_after_commit(
    *,
    graph: ClaimGraph,
    apply_result: ApplyResult,
    entity_instructions_by_claim: EntityInstructionsByClaim,
    association_instructions_by_claim: AssociationInstructionsByClaim,
) -> None:
    for tracked_object in _tracked_objects_for_clear(
        graph=graph,
        apply_result=apply_result,
        entity_instructions_by_claim=entity_instructions_by_claim,
        association_instructions_by_claim=association_instructions_by_claim,
    ):
        tracked_object.clear_changed_fields()


def _tracked_objects_for_clear(
    *,
    graph: ClaimGraph,
    apply_result: ApplyResult,
    entity_instructions_by_claim: EntityInstructionsByClaim,
    association_instructions_by_claim: AssociationInstructionsByClaim,
) -> tuple[Entity, ...]:
    tracked_objects: list[Entity] = []
    seen: set[int] = set()
    for candidate in _tracked_clear_candidates(
        graph=graph,
        apply_result=apply_result,
        entity_instructions_by_claim=entity_instructions_by_claim,
        association_instructions_by_claim=association_instructions_by_claim,
    ):
        _add_tracked_object(candidate, tracked_objects=tracked_objects, seen=seen)
    return tuple(tracked_objects)


def _tracked_clear_candidates(
    *,
    graph: ClaimGraph,
    apply_result: ApplyResult,
    entity_instructions_by_claim: EntityInstructionsByClaim,
    association_instructions_by_claim: AssociationInstructionsByClaim,
) -> tuple[object, ...]:
    candidates: list[object] = [claim.entity for claim in graph.claims]
    candidates.extend(
        relationship.payload
        for relationship in graph.relationships
        if isinstance(relationship, AssociationClaim)
    )
    candidates.extend(_instruction_targets(entity_instructions_by_claim.values()))
    candidates.extend(_instruction_targets(association_instructions_by_claim.values()))
    candidates.extend(apply_result.entities_by_claim.values())
    candidates.extend(apply_result.associations_by_claim.values())
    return tuple(candidates)


def _instruction_targets(
    instructions: Iterable[object],
) -> tuple[object, ...]:
    targets: list[object] = []
    for instruction in instructions:
        if isinstance(instruction, MergeInstruction):
            targets.append(cast("Any", instruction).target)
            continue
        if isinstance(instruction, NoopInstruction):
            targets.append(cast("Any", instruction).target)
    return tuple(targets)


def _add_tracked_object(
    candidate: object,
    *,
    tracked_objects: list[Entity],
    seen: set[int],
) -> None:
    if not isinstance(candidate, Entity):
        return
    marker = id(candidate)
    if marker in seen:
        return
    tracked_objects.append(candidate)
    seen.add(marker)


def _normalization_keys(claim_keys: tuple[ClaimKey, ...]) -> tuple[tuple[object, ...], ...]:
    return tuple(tuple(part for part in key) for key in claim_keys)


def _keys_for_entity(
    found: dict[tuple[object, ...], IdentifiedEntity],
    *,
    entity: IdentifiedEntity,
) -> set[tuple[object, ...]]:
    return {
        key
        for key, found_entity in found.items()
        if found_entity.entity_type == entity.entity_type
        and found_entity.resolved_id == entity.resolved_id
    }
