"""SQLAlchemy-backed unit of work for play-event persistence."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sortipy.adapters.sqlalchemy import (
    SqlAlchemyPlayEventRepository,
    create_all_tables,
    start_mappers,
)
from sortipy.common.storage import get_database_uri
from sortipy.domain.ports.unit_of_work import PlayEventRepositories

if TYPE_CHECKING:
    from types import TracebackType

    from sortipy.domain.ports.unit_of_work import PlayEventUnitOfWork


DATABASE_URI = get_database_uri()
ENGINE = create_engine(DATABASE_URI, future=True)


def startup() -> None:
    """Initialize database tables and ORM mappings."""

    start_mappers()
    create_all_tables(ENGINE)


def get_unit_of_work() -> PlayEventUnitOfWork:
    """Return a new SQLAlchemy-backed unit of work."""

    return SqlAlchemyUnitOfWork()


class SqlAlchemyUnitOfWork:
    """Unit of work managing SQLAlchemy sessions for play events."""

    def __init__(self) -> None:
        self.session_factory = sessionmaker(bind=ENGINE)

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        self.session = self.session_factory()
        self.repositories = PlayEventRepositories(
            play_events=SqlAlchemyPlayEventRepository(self.session)
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
        self.session.close()
        return False

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()


if TYPE_CHECKING:
    _uow_check: PlayEventUnitOfWork = SqlAlchemyUnitOfWork()
