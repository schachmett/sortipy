"""Tests for SQLAlchemy repositories."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session  # noqa: TC002

from sortipy.adapters.sqlalchemy.repositories import SqlAlchemyPlayEventRepository
from sortipy.domain.model import Provider
from tests.helpers.play_events import make_play_event


def test_play_event_repository_tracks_latest_timestamp(sqlite_session: Session) -> None:
    repository = SqlAlchemyPlayEventRepository(sqlite_session)
    base_time = datetime.now(tz=UTC).replace(microsecond=0)
    first = make_play_event("First", timestamp=base_time)
    second = make_play_event("Second", timestamp=base_time + timedelta(minutes=5))

    sqlite_session.add_all([first.user, second.user])
    sqlite_session.commit()

    repository.add(first)
    repository.add(second)
    sqlite_session.commit()

    assert repository.exists(user_id=first.user.id, source=first.source, played_at=base_time)
    assert repository.exists(
        user_id=second.user.id, source=second.source, played_at=second.played_at
    )
    assert repository.latest_timestamp() == second.played_at


def test_play_event_repository_latest_timestamp_empty(sqlite_session: Session) -> None:
    repository = SqlAlchemyPlayEventRepository(sqlite_session)

    assert repository.latest_timestamp() is None


def test_play_event_repository_exists_returns_false_for_missing_rows(
    sqlite_session: Session,
) -> None:
    repository = SqlAlchemyPlayEventRepository(sqlite_session)
    timestamp = datetime.now(tz=UTC)

    assert (
        repository.exists(
            user_id=uuid.uuid4(),
            source=Provider.LASTFM,
            played_at=timestamp,
        )
        is False
    )
