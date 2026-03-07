"""Persistence contracts and implementation for reconciliation output.

Responsibilities of this stage:
- persist newly created canonical/user entities
- persist normalization sidecars for resolved claims
- commit transaction boundaries on the provided unit of work
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from sortipy.domain.model import (
    Artist,
    Label,
    LibraryItem,
    PlayEvent,
    Recording,
    Release,
    ReleaseSet,
    User,
)
from sortipy.domain.ports.unit_of_work import RepositoryCollection, UnitOfWork

from .contracts import (
    CreateInstruction,
    ManualReviewInstruction,
    MergeInstruction,
    NoopInstruction,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sortipy.domain.model import (
        IdentifiedEntity,
    )
    from sortipy.domain.ports.persistence import (
        ArtistRepository,
        LabelRepository,
        LibraryItemRepository,
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

    _ = (association_instructions_by_claim, link_instructions_by_claim, apply_result)

    persisted_entities = 0
    persisted_sidecars = 0

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

    uow.commit()
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
