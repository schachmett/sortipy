from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal, Protocol

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sortipy.adapters.sqlalchemy import LastFMScrobbleRepository, create_all_tables, start_mappers

if TYPE_CHECKING:
    from types import TracebackType

    from sortipy.common.repository import Repository
    from sortipy.domain.types import LastFMScrobble


class UnitOfWork(Protocol):
    scrobbles: Repository[LastFMScrobble]

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(
        self, exc_type: type[BaseException], exc_value: BaseException, traceback: TracebackType
    ) -> Literal[False]: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


ENGINE = create_engine(os.environ["DATABASE_URI"], future=True)


def startup() -> None:
    """Initialize the database."""
    start_mappers()
    create_all_tables(ENGINE)


def get_unit_of_work() -> UnitOfWork:
    """Get a new unit of work."""
    return SqlAlchemyUnitOfWork()


class SqlAlchemyUnitOfWork(UnitOfWork):
    def __init__(self) -> None:
        self.session_factory = sessionmaker(bind=ENGINE)

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        self.session = self.session_factory()
        self.scrobbles = LastFMScrobbleRepository(self.session)
        return self

    def __exit__(
        self, exc_type: type[BaseException], exc_value: BaseException, traceback: TracebackType
    ) -> Literal[False]:
        self.session.close()
        return False  # don't swallow exceptions

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
