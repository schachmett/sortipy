"""Unit-of-work abstractions for coordinating repositories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from types import TracebackType

    from sortipy.domain.ports.persistence import PlayEventRepository


@runtime_checkable
class RepositoryCollection(Protocol):
    """Marker protocol for groups of repositories managed together."""


@runtime_checkable
class UnitOfWork[TRepositories: RepositoryCollection](Protocol):
    """Generic unit-of-work boundary around a repository collection."""

    repositories: TRepositories

    def __enter__(self) -> UnitOfWork[TRepositories]: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@dataclass(slots=True)
class PlayEventRepositories(RepositoryCollection):
    """Repositories required to persist play events."""

    play_events: PlayEventRepository


type PlayEventUnitOfWork = UnitOfWork[PlayEventRepositories]


__all__ = [
    "PlayEventRepositories",
    "PlayEventUnitOfWork",
    "RepositoryCollection",
    "UnitOfWork",
]
