"""Unit-of-work abstractions for coordinating repositories."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from types import TracebackType

    from .persistence import (
        ArtistRepository,
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


@runtime_checkable
class CatalogRepositories(RepositoryCollection, Protocol):
    """Repositories for canonical catalog entities."""

    @property
    def artists(self) -> ArtistRepository: ...
    @property
    def release_sets(self) -> ReleaseSetRepository: ...
    @property
    def releases(self) -> ReleaseRepository: ...
    @property
    def recordings(self) -> RecordingRepository: ...
