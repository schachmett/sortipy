from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine  # noqa: TC002
from sqlalchemy.orm import Session, sessionmaker

from sortipy.adapters.lastfm import RecentTracksResponse
from sortipy.adapters.sqlalchemy import start_mappers
from sortipy.adapters.sqlalchemy.migrations import upgrade_head
from sortipy.adapters.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork, shutdown, startup

os.environ.setdefault("DATABASE_URI", "sqlite+pysqlite:///:memory:")

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


@pytest.fixture(scope="session")
def recent_tracks_payloads() -> tuple[RecentTracksResponse, ...]:
    path = Path(__file__).resolve().parent / "data" / "lastfm_recent_tracks.jsonl"
    with path.open() as handle:
        return tuple(cast(RecentTracksResponse, json.loads(line)) for line in handle)


@pytest.fixture
def sqlite_engine() -> Iterator[Engine]:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    start_mappers()
    upgrade_head(engine=engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def sqlite_session(sqlite_engine: Engine) -> Iterator[Session]:
    session_factory = sessionmaker(bind=sqlite_engine, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def sqlite_unit_of_work(
    sqlite_engine: Engine,
) -> Iterator[Callable[[], SqlAlchemyUnitOfWork]]:
    startup(engine=sqlite_engine, force=True)

    def factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork()

    try:
        yield factory
    finally:
        shutdown()
