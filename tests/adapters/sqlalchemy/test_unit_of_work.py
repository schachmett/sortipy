from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import create_engine

from sortipy.adapters.sqlalchemy.unit_of_work import (
    SqlAlchemyUnitOfWork,
    StartupError,
    create_unit_of_work_factory,
)
from tests.helpers.play_events import make_play_event

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


def test_unit_of_work_factory_requires_engine_or_uri() -> None:
    with pytest.raises(StartupError):
        create_unit_of_work_factory()


def test_unit_of_work_factory_accepts_engine() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    factory = create_unit_of_work_factory(engine=engine)
    uow = factory()
    assert isinstance(uow, SqlAlchemyUnitOfWork)


def test_unit_of_work_persists_events(sqlite_engine: Engine) -> None:
    factory = create_unit_of_work_factory(engine=sqlite_engine)

    with factory() as uow:
        event = make_play_event("Persisted", timestamp=datetime.now(tz=UTC))
        uow.repositories.users.add(event.user)
        uow.repositories.play_events.add(event)
        uow.commit()

    with factory() as uow:
        repo = uow.repositories.play_events
        assert repo.latest_timestamp() is not None
        assert repo.exists(event)
