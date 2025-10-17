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
from sortipy.domain.data_integration import PlayEventUnitOfWork

if TYPE_CHECKING:
    from types import TracebackType


DATABASE_URI = get_database_uri()
ENGINE = create_engine(DATABASE_URI, future=True)


def startup() -> None:
    """Initialize the database."""
    start_mappers()
    create_all_tables(ENGINE)


def get_unit_of_work() -> PlayEventUnitOfWork:
    """Get a new unit of work."""
    return SqlAlchemyUnitOfWork()


class SqlAlchemyUnitOfWork(PlayEventUnitOfWork):
    def __init__(self) -> None:
        self.session_factory = sessionmaker(bind=ENGINE)

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        self.session = self.session_factory()
        self.play_events = SqlAlchemyPlayEventRepository(self.session)
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
        return False  # don't swallow exceptions

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
