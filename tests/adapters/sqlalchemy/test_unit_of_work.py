from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import create_engine

from sortipy.adapters.sqlalchemy.unit_of_work import (
    SqlAlchemyUnitOfWork,
    StartupError,
    configured_engine,
    shutdown,
    startup,
)
from tests.helpers.play_events import make_play_event

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.engine import Engine


@pytest.fixture(autouse=True)
def reset_unit_of_work_state() -> Iterator[None]:
    shutdown()
    yield
    shutdown()


def test_sqlalchemy_unit_of_work_requires_startup() -> None:
    with pytest.raises(StartupError):
        SqlAlchemyUnitOfWork()


def test_startup_requires_force_for_reconfiguration() -> None:
    engine_a = create_engine("sqlite+pysqlite:///:memory:", future=True)
    engine_b = create_engine("sqlite+pysqlite:///:memory:", future=True)

    startup(engine=engine_a, force=True)

    with pytest.raises(StartupError):
        startup(engine=engine_b)

    startup(engine=engine_b, force=True)
    assert configured_engine() is engine_b


def test_unit_of_work_persists_events(sqlite_engine: Engine) -> None:
    startup(engine=sqlite_engine, force=True)

    with SqlAlchemyUnitOfWork() as uow:
        event = make_play_event("Persisted", timestamp=datetime.now(tz=UTC))
        uow.repositories.users.add(event.user)
        uow.repositories.play_events.add(event)
        uow.commit()
        played_at = event.played_at

    with SqlAlchemyUnitOfWork() as uow:
        repo = uow.repositories.play_events
        assert repo.latest_timestamp() is not None
        assert repo.exists(user_id=event.user.id, source=event.source, played_at=played_at)
