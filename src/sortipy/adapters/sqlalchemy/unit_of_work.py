"""SQLAlchemy-backed unit of work for play-event persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from sortipy.adapters.sqlalchemy import (
    SqlAlchemyPlayEventRepository,
    create_all_tables,
    start_mappers,
)
from sortipy.common.storage import get_database_uri
from sortipy.domain.ports.unit_of_work import PlayEventRepositories, PlayEventUnitOfWork

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
            self._session_factory = sessionmaker(bind=self._engine)
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
    create_all_tables(resolved_engine)
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


class SqlAlchemyUnitOfWork:
    """Unit of work managing SQLAlchemy sessions for play events."""

    def __init__(self) -> None:
        self.session_factory: sessionmaker[Session] = _STATE.session_factory
        self._session: Session | None = None

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        self._session = self.session_factory()
        self.repositories = PlayEventRepositories(
            play_events=SqlAlchemyPlayEventRepository(self._session)
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        if exc_type is not None:
            self.rollback()
        if self._session is not None:
            self._session.close()
            self._session = None
        return False

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    @property
    def session(self) -> Session:
        if self._session is None:
            raise StartupError("Unit of work session not initialised")
        return self._session

    @property
    def is_open(self) -> bool:
        return self._session is not None


if TYPE_CHECKING:
    from sortipy.domain.ports.unit_of_work import PlayEventUnitOfWork

    _uow_check: PlayEventUnitOfWork = SqlAlchemyUnitOfWork()
