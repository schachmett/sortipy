"""Reusable fakes and helpers for library-item related tests."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Self, cast

from sortipy.domain.model import (
    Artist,
    ArtistRole,
    Label,
    Provider,
    Recording,
    Release,
    ReleaseSet,
    User,
)
from sortipy.domain.ports.fetching import LibraryItemFetcher, LibraryItemFetchResult

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from uuid import UUID

    from sortipy.domain.model import (
        Entity,
        EntityType,
        IdentifiedEntity,
        LibraryItem,
        Namespace,
        PlayEvent,
    )
    from sortipy.domain.ports.persistence import PriorityKeysData
    from sortipy.domain.reconciliation.persist import ReconciliationUnitOfWork


def make_recording_library_item(user: User | None = None) -> LibraryItem:
    artist = Artist(name="Example Artist")
    release_set = ReleaseSet(title="Example Release Set")
    release = release_set.create_release(title="Example Release")
    recording = Recording(title="Example Recording")
    release_set.add_artist(artist, role=ArtistRole.PRIMARY)
    recording.add_artist(artist, role=ArtistRole.PRIMARY)
    release.add_track(recording)

    owner = user or User(display_name="Example User")
    return owner.save_entity(recording, source=Provider.SPOTIFY)


def make_release_set_library_item(user: User | None = None) -> LibraryItem:
    artist = Artist(name="Example Artist")
    release_set = ReleaseSet(title="Example Release Set")
    release_set.add_artist(artist, role=ArtistRole.PRIMARY)

    owner = user or User(display_name="Example User")
    return owner.save_entity(release_set, source=Provider.SPOTIFY)


def make_artist_library_item(user: User | None = None) -> LibraryItem:
    owner = user or User(display_name="Example User")
    artist = Artist(name="Example Artist")
    return owner.save_entity(artist, source=Provider.SPOTIFY)


class FakeLibraryItemSource(LibraryItemFetcher):
    """In-memory implementation of the library-item source port for testing."""

    def __init__(self, items: Iterable[LibraryItem]) -> None:
        self._items = list(items)
        self.calls: list[dict[str, object]] = []

    def __call__(
        self,
        *,
        user: User,
        batch_size: int = 50,
        max_tracks: int | None = None,
        max_albums: int | None = None,
        max_artists: int | None = None,
    ) -> LibraryItemFetchResult:
        self.calls.append(
            {
                "user": user,
                "batch_size": batch_size,
                "max_tracks": max_tracks,
                "max_albums": max_albums,
                "max_artists": max_artists,
            }
        )
        return LibraryItemFetchResult(library_items=list(self._items))


class FakeLibraryItemRepository:
    """Simple in-memory repository for library items."""

    def __init__(self, initial: Iterable[LibraryItem] | None = None) -> None:
        self.items: list[LibraryItem] = list(initial or [])

    def add(self, entity: LibraryItem) -> None:
        self.items.append(entity)

    def exists(
        self,
        *,
        user_id: object,
        target_type: EntityType,
        target_id: object,
    ) -> bool:
        return any(
            item.user.id == user_id
            and item.target_type is target_type
            and item.target_id == target_id
            for item in self.items
        )


class _NullCanonicalRepository[TCanonical]:
    def add(self, entity: TCanonical) -> None:
        _ = entity

    def get_by_external_id(self, namespace: Namespace, value: str) -> TCanonical | None:
        _ = (namespace, value)
        return None

    def find_by_normalized_key(self, key: tuple[object, ...]) -> tuple[TCanonical, ...]:
        _ = key
        return ()

    def list(self, *, limit: int | None = None) -> list[TCanonical]:
        _ = limit
        return []


class _NullSidecarRepository:
    def save(
        self,
        entity: IdentifiedEntity,
        data: PriorityKeysData,
    ) -> None:  # pragma: no cover - trivial
        _ = (entity, data)

    def find_by_keys(
        self,
        entity_type: EntityType,
        keys: tuple[tuple[object, ...], ...],
    ) -> dict[tuple[object, ...], IdentifiedEntity]:
        _ = (entity_type, keys)
        return {}


class _NullUserRepository:
    def add(self, entity: User) -> None:
        _ = entity

    def get(self, user_id: UUID) -> User | None:
        _ = user_id
        return None


class _NullPlayEventRepository:
    def add(self, entity: PlayEvent) -> None:
        _ = entity

    def exists(self, event: PlayEvent) -> bool:
        _ = event
        return False

    def latest_timestamp(self) -> None:
        return None


class _NullMutationRepository:
    def attach_created(self, entity: Entity) -> None:
        _ = entity

    def update(self, entity: Entity, *, changed_fields: frozenset[str]) -> None:
        _ = (entity, changed_fields)


@dataclass(slots=True)
class _FakeLibraryItemRepositories:
    library_items: FakeLibraryItemRepository
    artists: _NullCanonicalRepository[Artist]
    labels: _NullCanonicalRepository[Label]
    release_sets: _NullCanonicalRepository[ReleaseSet]
    releases: _NullCanonicalRepository[Release]
    recordings: _NullCanonicalRepository[Recording]
    users: _NullUserRepository
    play_events: _NullPlayEventRepository
    normalization_sidecars: _NullSidecarRepository
    mutations: _NullMutationRepository


class FakeIngestUnitOfWork:
    """Unit of work capturing library-item persistence interactions."""

    def __init__(self, repository: FakeLibraryItemRepository) -> None:
        self.repositories = _FakeLibraryItemRepositories(
            library_items=repository,
            artists=_NullCanonicalRepository[Artist](),
            labels=_NullCanonicalRepository[Label](),
            release_sets=_NullCanonicalRepository[ReleaseSet](),
            releases=_NullCanonicalRepository[Release](),
            recordings=_NullCanonicalRepository[Recording](),
            users=_NullUserRepository(),
            play_events=_NullPlayEventRepository(),
            normalization_sidecars=_NullSidecarRepository(),
            mutations=_NullMutationRepository(),
        )
        self.committed = False
        self.rollback_called = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> Literal[False]:
        if exc_type is not None:
            self.rollback()
        return False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rollback_called = True

    def suspend_autoflush(self) -> contextlib.AbstractContextManager[object]:
        return contextlib.nullcontext(cast("object", None))


def make_reconciliation_uow_factory(
    repository_or_uow: FakeLibraryItemRepository | FakeIngestUnitOfWork,
) -> Callable[[], ReconciliationUnitOfWork]:
    def factory() -> ReconciliationUnitOfWork:
        uow = (
            repository_or_uow
            if isinstance(repository_or_uow, FakeIngestUnitOfWork)
            else FakeIngestUnitOfWork(repository_or_uow)
        )
        return cast("ReconciliationUnitOfWork", uow)

    return factory


if TYPE_CHECKING:
    from sortipy.domain.ports.persistence import LibraryItemRepository

    _check_repo: LibraryItemRepository = FakeLibraryItemRepository()
    _uow_check = cast("ReconciliationUnitOfWork", FakeIngestUnitOfWork(_check_repo))
