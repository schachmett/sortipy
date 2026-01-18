"""SQLAlchemy-backed units of work for play events and ingest pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from sortipy.domain.ports import RepositoryCollection

from .mappings import start_mappers
from .migrations import upgrade_head
from .repositories import (
    MissingParentError,
    SqlAlchemyArtistRepository,
    SqlAlchemyLibraryItemRepository,
    SqlAlchemyNormalizationSidecarRepository,
    SqlAlchemyPlayEventRepository,
    SqlAlchemyRecordingRepository,
    SqlAlchemyReleaseRepository,
    SqlAlchemyReleaseSetRepository,
    SqlAlchemyUserRepository,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    from sqlalchemy.engine import Engine


class StartupError(RuntimeError):
    """Raised when a SQLAlchemy unit of work cannot be initialised."""


class BaseSqlAlchemyUnitOfWork[TRepositories: RepositoryCollection](ABC):
    """Generic SQLAlchemy unit of work with pluggable repository collections."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory
        self._session: Session | None = None

    @abstractmethod
    def _build_repositories(self, session: Session) -> TRepositories: ...

    def __enter__(self) -> BaseSqlAlchemyUnitOfWork[TRepositories]:
        self.session = self.session_factory()
        self._repositories = self._build_repositories(self.session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        if exc_type is not None:
            self.rollback()
        self.session.close()
        self.session = None
        return False

    def commit(self) -> None:
        try:
            self.session.commit()
        except IntegrityError as exc:
            message = str(exc.orig)
            if (
                "NOT NULL constraint failed" in message
                or "FOREIGN KEY constraint failed" in message
            ):
                raise MissingParentError(
                    f"Integrity error during commit: {message}", exc.params
                ) from exc
            raise

    def rollback(self) -> None:
        self.session.rollback()

    @property
    def repositories(self) -> TRepositories:
        if self._session is None:
            raise StartupError("Unit of work session not initialised")
        return self._repositories

    @property
    def session(self) -> Session:
        if self._session is None:
            raise StartupError("Unit of work session not initialised")
        return self._session

    @session.setter
    def session(self, session: Session | None) -> None:
        if self._session is not None and session is not None:
            raise StartupError("Unit of work session already initialised")
        self._session = session


@dataclass(slots=True)
class SqlAlchemyRepositories(RepositoryCollection):
    play_events: SqlAlchemyPlayEventRepository
    library_items: SqlAlchemyLibraryItemRepository
    users: SqlAlchemyUserRepository
    artists: SqlAlchemyArtistRepository
    release_sets: SqlAlchemyReleaseSetRepository
    releases: SqlAlchemyReleaseRepository
    recordings: SqlAlchemyRecordingRepository
    normalization_sidecars: SqlAlchemyNormalizationSidecarRepository


class SqlAlchemyUnitOfWork(BaseSqlAlchemyUnitOfWork[SqlAlchemyRepositories]):
    """Unit of work providing all SQLAlchemy repositories."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        super().__init__(session_factory)

    def _build_repositories(self, session: Session) -> SqlAlchemyRepositories:
        return SqlAlchemyRepositories(
            play_events=SqlAlchemyPlayEventRepository(session),
            library_items=SqlAlchemyLibraryItemRepository(session),
            users=SqlAlchemyUserRepository(session),
            artists=SqlAlchemyArtistRepository(session),
            release_sets=SqlAlchemyReleaseSetRepository(session),
            releases=SqlAlchemyReleaseRepository(session),
            recordings=SqlAlchemyRecordingRepository(session),
            normalization_sidecars=SqlAlchemyNormalizationSidecarRepository(session),
        )


def create_unit_of_work_factory(
    *,
    engine: Engine | None = None,
    database_uri: str | None = None,
) -> Callable[[], SqlAlchemyUnitOfWork]:
    """Create a unit-of-work factory from an engine or database URI."""

    if engine is None and database_uri is None:
        raise StartupError("create_unit_of_work_factory requires an Engine or database_uri")
    resolved_engine = engine if database_uri is None else create_engine(database_uri, future=True)

    start_mappers()
    upgrade_head(engine=resolved_engine)

    session_factory = sessionmaker(bind=resolved_engine, expire_on_commit=False)

    def factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return factory


if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from sortipy.domain.ingest_pipeline import (
        IngestionUnitOfWork,
        LibraryItemSyncUnitOfWork,
        PlayEventSyncUnitOfWork,
    )

    _factory = create_unit_of_work_factory(database_uri="sqlite+pysqlite:///:memory:")
    _uow_check: IngestionUnitOfWork = _factory()
    _uow_pe_check: PlayEventSyncUnitOfWork = _factory()
    _uow_li_check: LibraryItemSyncUnitOfWork = _factory()
