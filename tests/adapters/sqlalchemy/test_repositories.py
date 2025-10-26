"""Tests for SQLAlchemy repositories."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session  # noqa: TC002

from sortipy.adapters.sqlalchemy import CanonicalEntityMerger
from sortipy.adapters.sqlalchemy.repositories import SqlAlchemyPlayEventRepository
from tests.helpers.play_events import make_play_event


@pytest.fixture
def merger(sqlite_session: Session) -> CanonicalEntityMerger:
    sqlite_session.expire_all()
    return CanonicalEntityMerger(sqlite_session)


def test_play_event_repository_tracks_latest_timestamp(sqlite_session: Session) -> None:
    repository = SqlAlchemyPlayEventRepository(sqlite_session)
    base_time = datetime.now(tz=UTC).replace(microsecond=0)
    first = make_play_event("First", timestamp=base_time)
    second = make_play_event("Second", timestamp=base_time + timedelta(minutes=5))

    repository.add(first)
    repository.add(second)
    sqlite_session.commit()

    assert repository.exists(base_time)
    assert repository.exists(second.played_at)
    assert repository.latest_timestamp() == second.played_at


def test_play_event_repository_latest_timestamp_empty(sqlite_session: Session) -> None:
    repository = SqlAlchemyPlayEventRepository(sqlite_session)

    assert repository.latest_timestamp() is None


def test_play_event_repository_exists_returns_false_for_missing_rows(
    sqlite_session: Session,
) -> None:
    repository = SqlAlchemyPlayEventRepository(sqlite_session)
    timestamp = datetime.now(tz=UTC)

    assert repository.exists(timestamp) is False
