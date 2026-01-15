"""SQLAlchemy-backed units of work for play events and ingest pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from sortipy.adapters.sqlalchemy import (
    SqlAlchemyArtistRepository,
    SqlAlchemyPlayEventRepository,
    SqlAlchemyRecordingRepository,
    SqlAlchemyReleaseRepository,
    SqlAlchemyReleaseSetRepository,
    start_mappers,
)
from sortipy.adapters.sqlalchemy.migrations import upgrade_head
from sortipy.adapters.sqlalchemy.repositories import (
    MissingParentError,
    SqlAlchemyLibraryItemRepository,
    SqlAlchemyNormalizationSidecarRepository,
    SqlAlchemyUserRepository,
)
from sortipy.common.storage import get_database_uri
from sortipy.domain.ports.unit_of_work import RepositoryCollection

if TYPE_CHECKING:
    from types import TracebackType

    from sqlalchemy.engine import Engine


class StartupError(RuntimeError):
    """Raised when a SQLAlchemy unit of work is used before initialisation."""


@dataclass(slots=True)
class _AdapterState:
    _engine: Engine | None = None
    _session_factory: sessionmaker[Session] | None = None

    @property
    def engine(self) -> Engine | None:
        return self._engine

    @engine.setter
    def engine(self, value: Engine | None) -> None:
        self._session_factory = None
        self._engine = value

    @property
    def session_factory(self) -> sessionmaker[Session]:
        if self._engine is None:
            raise StartupError(
                "SQLAlchemy adapter not initialised. Call sortipy.adapters.sqlalchemy."
                "unit_of_work.startup() before requesting a unit of work."
            )
        if self._session_factory is None:
            self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)
        return self._session_factory


_STATE = _AdapterState()


def startup(
    *,
    engine: Engine | None = None,
    database_uri: str | None = None,
    force: bool = False,
) -> None:
    """Initialise the SQLAlchemy engine, metadata, and session factory."""

    if _STATE.engine is not None and not force:
        raise StartupError(
            "SQLAlchemy adapter already initialised. Pass force=True to reconfigure."
        )

    resolved_engine = engine or create_engine(database_uri or get_database_uri(), future=True)
    start_mappers()
    upgrade_head(engine=resolved_engine)

    _STATE.engine = resolved_engine


def configured_engine() -> Engine | None:
    """Return the engine currently managed by the adapter (if any)."""

    return _STATE.engine


def is_started() -> bool:
    """Return whether the adapter has been initialised."""

    return _STATE.engine is not None


def shutdown() -> None:
    """Dispose the managed engine and reset state (primarily for tests)."""

    if _STATE.engine is not None:
        _STATE.engine.dispose()
    _STATE.engine = None


class BaseSqlAlchemyUnitOfWork[TRepositories: RepositoryCollection](ABC):
    """Generic SQLAlchemy unit of work with pluggable repository collections."""

    def __init__(self) -> None:
        self.session_factory: sessionmaker[Session] = _STATE.session_factory
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


if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from sortipy.domain.ingest_pipeline.ingest_ports import (
        IngestionUnitOfWork,
        LibraryItemSyncUnitOfWork,
        PlayEventSyncUnitOfWork,
    )

    _uow_check: IngestionUnitOfWork = SqlAlchemyUnitOfWork()
    _uow_pe_check: PlayEventSyncUnitOfWork = SqlAlchemyUnitOfWork()
    _uow_li_check: LibraryItemSyncUnitOfWork = SqlAlchemyUnitOfWork()
