"""Unit-of-work abstractions for coordinating repositories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from types import TracebackType

    from sortipy.domain.ports.persistence import (
        ArtistRepository,
        PlayEventRepository,
        RecordingRepository,
        ReleaseRepository,
        ReleaseSetRepository,
    )


@runtime_checkable
class RepositoryCollection(Protocol):
    """Marker protocol for groups of repositories managed together."""


@runtime_checkable
class UnitOfWork[TRepositories: RepositoryCollection](Protocol):
    """Generic unit-of-work boundary around a repository collection."""

    @property
    def repositories(self) -> TRepositories: ...  # the repo list itself should be immutable

    def __enter__(self) -> UnitOfWork[TRepositories]: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@dataclass(slots=True)
class PlayEventRepositories(RepositoryCollection):
    """Repositories required to persist play events."""

    play_events: PlayEventRepository
    artists: ArtistRepository
    release_sets: ReleaseSetRepository
    releases: ReleaseRepository
    recordings: RecordingRepository


type PlayEventUnitOfWork = UnitOfWork[PlayEventRepositories]
