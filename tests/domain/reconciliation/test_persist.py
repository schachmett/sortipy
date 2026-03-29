from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self, cast

from sortipy.domain.model import (
    Artist,
    Provider,
    Recording,
    Release,
    ReleaseSet,
)
from sortipy.domain.reconciliation import (
    AssociationClaim,
    AssociationKind,
    ClaimGraph,
    ClaimMetadata,
    EntityClaim,
)
from sortipy.domain.reconciliation.apply import ApplyResult
from sortipy.domain.reconciliation.contracts import CreateInstruction, MergeInstruction
from sortipy.domain.reconciliation.persist import persist_reconciliation

if TYPE_CHECKING:
    from sortipy.domain.model import (
        Entity,
        EntityType,
        IdentifiedEntity,
        Label,
        LibraryItem,
        PlayEvent,
    )
    from sortipy.domain.ports.persistence import PriorityKeysData
    from sortipy.domain.reconciliation.persist import ReconciliationUnitOfWork


class _NullRepository[TEntity]:
    def __init__(self) -> None:
        self.added: list[TEntity] = []

    def add(self, entity: TEntity) -> None:
        self.added.append(entity)


class _NullSidecarRepository:
    def save(self, entity: IdentifiedEntity, data: PriorityKeysData) -> None:
        _ = (entity, data)

    def find_by_keys(
        self,
        entity_type: EntityType,
        keys: tuple[tuple[object, ...], ...],
    ) -> dict[tuple[object, ...], IdentifiedEntity]:
        _ = (entity_type, keys)
        return {}


class _RecordingRepository(_NullRepository[Recording]):
    def list(self, *, limit: int | None = None) -> list[Recording]:
        _ = limit
        return []


class _ReleaseRepository(_NullRepository[Release]):
    def list(self, *, limit: int | None = None) -> list[Release]:
        _ = limit
        return []


@dataclass(slots=True)
class _MutationCall:
    entity: Entity
    changed_fields: frozenset[str]


@dataclass(slots=True)
class _AttachCall:
    entity: Entity


class _FakeMutationRepository:
    def __init__(self) -> None:
        self.calls: list[_MutationCall] = []
        self.attach_calls: list[_AttachCall] = []

    def attach_created(self, entity: Entity) -> None:
        self.attach_calls.append(_AttachCall(entity=entity))

    def update(self, entity: Entity, *, changed_fields: frozenset[str]) -> None:
        self.calls.append(_MutationCall(entity=entity, changed_fields=changed_fields))


def _new_artist_repo() -> _NullRepository[Artist]:
    return _NullRepository()


def _new_label_repo() -> _NullRepository[Label]:
    return _NullRepository()


def _new_release_set_repo() -> _NullRepository[ReleaseSet]:
    return _NullRepository()


def _new_user_repo() -> _NullRepository[object]:
    return _NullRepository()


def _new_library_item_repo() -> _NullRepository[LibraryItem]:
    return _NullRepository()


def _new_play_event_repo() -> _NullRepository[PlayEvent]:
    return _NullRepository()


@dataclass(slots=True)
class _FakeRepositories:
    artists: _NullRepository[Artist] = field(default_factory=_new_artist_repo)
    labels: _NullRepository[Label] = field(default_factory=_new_label_repo)
    release_sets: _NullRepository[ReleaseSet] = field(default_factory=_new_release_set_repo)
    releases: _ReleaseRepository = field(default_factory=_ReleaseRepository)
    recordings: _RecordingRepository = field(default_factory=_RecordingRepository)
    users: _NullRepository[object] = field(default_factory=_new_user_repo)
    library_items: _NullRepository[LibraryItem] = field(default_factory=_new_library_item_repo)
    play_events: _NullRepository[PlayEvent] = field(default_factory=_new_play_event_repo)
    normalization_sidecars: _NullSidecarRepository = field(default_factory=_NullSidecarRepository)
    mutations: _FakeMutationRepository = field(default_factory=_FakeMutationRepository)


class _FakeUnitOfWork:
    def __init__(self) -> None:
        self.repositories = _FakeRepositories()
        self.committed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> bool:
        _ = (exc_type, exc_value, traceback)
        return False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.committed = False

    def suspend_autoflush(self) -> object:
        return object()


def test_persist_reconciliation_updates_dirty_merge_targets_and_clears_flags() -> None:
    claim = EntityClaim(
        entity=Artist(name="Incoming"),
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    graph = ClaimGraph()
    graph.add(claim)

    merge_target = Artist(name="Canonical")
    merge_target.add_source(Provider.MUSICBRAINZ)

    uow = _FakeUnitOfWork()
    result = persist_reconciliation(
        graph=graph,
        keys_by_claim={},
        entity_instructions_by_claim={claim.claim_id: MergeInstruction(target=merge_target)},
        association_instructions_by_claim={},
        link_instructions_by_claim={},
        apply_result=ApplyResult(),
        uow=cast("ReconciliationUnitOfWork", uow),
    )

    assert result.committed is True
    assert uow.committed is True
    assert uow.repositories.mutations.calls == [
        _MutationCall(
            entity=merge_target,
            changed_fields=frozenset({"provenance"}),
        )
    ]
    assert merge_target.changed_fields == frozenset()


def test_persist_reconciliation_clears_created_entity_dirty_flags_after_commit() -> None:
    artist = Artist(name="Created")
    artist.add_source(Provider.SPOTIFY)
    claim = EntityClaim(
        entity=artist,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(claim)

    uow = _FakeUnitOfWork()
    persist_reconciliation(
        graph=graph,
        keys_by_claim={},
        entity_instructions_by_claim={claim.claim_id: CreateInstruction()},
        association_instructions_by_claim={},
        link_instructions_by_claim={},
        apply_result=ApplyResult(),
        uow=cast("ReconciliationUnitOfWork", uow),
    )

    assert uow.repositories.artists.added == [artist]
    assert artist.changed_fields == frozenset()


def test_persist_reconciliation_attaches_created_associations_before_commit() -> None:
    release_set = ReleaseSet(title="Mezzanine")
    artist = Artist(name="Massive Attack")
    contribution = release_set.add_artist(artist)

    source_claim = EntityClaim(
        entity=release_set,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    target_claim = EntityClaim(
        entity=artist,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    association_claim = AssociationClaim(
        source_claim_id=source_claim.claim_id,
        target_claim_id=target_claim.claim_id,
        kind=AssociationKind.RELEASE_SET_CONTRIBUTION,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
        payload=contribution,
    )
    graph = ClaimGraph()
    graph.add(source_claim)
    graph.add(target_claim)
    graph.add_relationship(association_claim)

    uow = _FakeUnitOfWork()
    persist_reconciliation(
        graph=graph,
        keys_by_claim={},
        entity_instructions_by_claim={},
        association_instructions_by_claim={association_claim.claim_id: CreateInstruction()},
        link_instructions_by_claim={},
        apply_result=ApplyResult(
            associations_by_claim={association_claim.claim_id: contribution},
        ),
        uow=cast("ReconciliationUnitOfWork", uow),
    )

    assert uow.repositories.mutations.attach_calls == [_AttachCall(entity=contribution)]
