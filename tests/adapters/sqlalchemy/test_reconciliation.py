from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sortipy.domain.model import Artist, EntityType, Provider
from sortipy.domain.reconciliation import (
    ClaimGraph,
    ClaimMetadata,
    CreateInstruction,
    EntityClaim,
    NoopInstruction,
)
from sortipy.domain.reconciliation.apply import ApplyResult
from sortipy.domain.reconciliation.persist import persist_reconciliation

if TYPE_CHECKING:
    from collections.abc import Callable

    from sortipy.adapters.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork
    from sortipy.domain.reconciliation.contracts import (
        AssociationInstructionsByClaim,
        EntityInstructionsByClaim,
        KeysByClaim,
        LinkInstructionsByClaim,
    )


@dataclass(slots=True)
class _PriorityKeysData:
    priority_keys: tuple[tuple[object, ...], ...]


def test_persist_reconciliation_commits_created_entities_and_sidecars(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    artist_claim = EntityClaim(
        entity=Artist(name="Massive Attack"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(artist_claim)

    keys_by_claim: KeysByClaim = {
        artist_claim.claim_id: (("artist:name", "massive attack"),),
    }
    entity_instructions_by_claim: EntityInstructionsByClaim = {
        artist_claim.claim_id: CreateInstruction(),
    }
    association_instructions_by_claim: AssociationInstructionsByClaim = {}
    link_instructions_by_claim: LinkInstructionsByClaim = {}

    with sqlite_unit_of_work() as uow:
        result = persist_reconciliation(
            graph=graph,
            keys_by_claim=keys_by_claim,
            entity_instructions_by_claim=entity_instructions_by_claim,
            association_instructions_by_claim=association_instructions_by_claim,
            link_instructions_by_claim=link_instructions_by_claim,
            apply_result=_empty_apply_result(),
            uow=uow,
        )

    assert result.committed is True
    assert result.persisted_entities == 1
    assert result.persisted_sidecars == 1

    with sqlite_unit_of_work() as uow:
        matches = uow.repositories.normalization_sidecars.find_by_keys(
            EntityType.ARTIST,
            (("artist:name", "massive attack"),),
        )

    matched = matches.get(("artist:name", "massive attack"))
    assert isinstance(matched, Artist)
    assert matched.name == "Massive Attack"


def test_persist_reconciliation_counts_only_new_sidecars(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    existing = Artist(name="Massive Attack")

    with sqlite_unit_of_work() as uow:
        uow.repositories.artists.add(existing)
        uow.repositories.normalization_sidecars.save(
            existing,
            _priority_keys_data((("artist:name", "massive attack"),)),
        )
        uow.commit()

    incoming_claim = EntityClaim(
        entity=Artist(name="MASSIVE ATTACK"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(incoming_claim)

    keys_by_claim: KeysByClaim = {
        incoming_claim.claim_id: (("artist:name", "massive attack"),),
    }
    entity_instructions_by_claim: EntityInstructionsByClaim = {
        incoming_claim.claim_id: NoopInstruction(target=existing),
    }
    association_instructions_by_claim: AssociationInstructionsByClaim = {}
    link_instructions_by_claim: LinkInstructionsByClaim = {}

    with sqlite_unit_of_work() as uow:
        result = persist_reconciliation(
            graph=graph,
            keys_by_claim=keys_by_claim,
            entity_instructions_by_claim=entity_instructions_by_claim,
            association_instructions_by_claim=association_instructions_by_claim,
            link_instructions_by_claim=link_instructions_by_claim,
            apply_result=_empty_apply_result(),
            uow=uow,
        )

    assert result.committed is True
    assert result.persisted_entities == 0
    assert result.persisted_sidecars == 0


def _empty_apply_result() -> ApplyResult:
    return ApplyResult()


def _priority_keys_data(priority_keys: tuple[tuple[object, ...], ...]) -> _PriorityKeysData:
    return _PriorityKeysData(priority_keys=priority_keys)
