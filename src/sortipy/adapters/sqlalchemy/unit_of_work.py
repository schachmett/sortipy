"""SQLAlchemy-backed units of work for play events and ingest pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from sortipy.adapters.sqlalchemy import (
    SqlAlchemyArtistRepository,
    SqlAlchemyPlayEventRepository,
    SqlAlchemyRecordingRepository,
    SqlAlchemyReleaseRepository,
    SqlAlchemyReleaseSetRepository,
    SqlAlchemyTrackRepository,
    start_mappers,
)
from sortipy.adapters.sqlalchemy.migrations import upgrade_head
from sortipy.adapters.sqlalchemy.repositories import SqlAlchemyNormalizationSidecarRepository
from sortipy.common.storage import get_database_uri
from sortipy.domain.ingest_pipeline.ingest_ports import IngestRepositories
from sortipy.domain.ports.unit_of_work import (
    PlayEventRepositories,
    RepositoryCollection,
)

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

    # temporary fix
    from sortipy.adapters.sqlalchemy.mappings import canonical_source_table  # noqa: PLC0415
    from sortipy.adapters.sqlalchemy.sidecar_mappings import (  # noqa: PLC0415
        normalization_sidecar_table,
    )

    canonical_source_table.create(resolved_engine, checkfirst=True)
    normalization_sidecar_table.create(resolved_engine, checkfirst=True)

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
        self.session.commit()

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


class SqlAlchemyPlayEventUnitOfWork(BaseSqlAlchemyUnitOfWork[PlayEventRepositories]):
    """Unit of work managing SQLAlchemy sessions for play events."""

    def _build_repositories(self, session: Session) -> PlayEventRepositories:
        return PlayEventRepositories(
            play_events=SqlAlchemyPlayEventRepository(session),
            artists=SqlAlchemyArtistRepository(session),
            release_sets=SqlAlchemyReleaseSetRepository(session),
            releases=SqlAlchemyReleaseRepository(session),
            recordings=SqlAlchemyRecordingRepository(session),
            tracks=SqlAlchemyTrackRepository(session),
        )


class SqlAlchemyIngestUnitOfWork(BaseSqlAlchemyUnitOfWork[IngestRepositories]):
    """Unit of work for ingest pipeline phases."""

    def _build_repositories(self, session: Session) -> IngestRepositories:
        return IngestRepositories(
            play_events=SqlAlchemyPlayEventRepository(session),
            artists=SqlAlchemyArtistRepository(session),
            release_sets=SqlAlchemyReleaseSetRepository(session),
            releases=SqlAlchemyReleaseRepository(session),
            recordings=SqlAlchemyRecordingRepository(session),
            tracks=SqlAlchemyTrackRepository(session),
            normalization_sidecars=SqlAlchemyNormalizationSidecarRepository(session),
        )


if TYPE_CHECKING:
    from sortipy.domain.ingest_pipeline.ingest_ports import IngestUnitOfWork
    from sortipy.domain.ports.unit_of_work import PlayEventUnitOfWork

    _uow_pe_check: PlayEventUnitOfWork = SqlAlchemyPlayEventUnitOfWork()
    _uow_ig_check: IngestUnitOfWork = SqlAlchemyIngestUnitOfWork()
