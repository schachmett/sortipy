"""Tests for SQLAlchemy repositories."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session  # noqa: TC002

from sortipy.adapters.sqlalchemy.repositories import (
    SqlAlchemyLibraryItemRepository,
    SqlAlchemyPlayEventRepository,
)
from sortipy.domain.model import Artist, User
from tests.helpers.play_events import make_play_event

if TYPE_CHECKING:
    from sortipy.domain.model import PlayEvent


def _persist_event_graph(
    sqlite_session: Session,
    event_name: str,
    *,
    timestamp: datetime,
) -> PlayEvent:
    event = make_play_event(event_name, timestamp=timestamp)
    artist = event.recording.contributions[0].artist
    release = event.release
    assert release is not None
    sqlite_session.add_all([event.user, artist, event.recording, release.release_set])
    sqlite_session.commit()
    return event


def test_play_event_repository_tracks_latest_timestamp(sqlite_session: Session) -> None:
    repository = SqlAlchemyPlayEventRepository(sqlite_session)
    base_time = datetime.now(tz=UTC).replace(microsecond=0)
    first = _persist_event_graph(sqlite_session, "First", timestamp=base_time)
    second = _persist_event_graph(
        sqlite_session,
        "Second",
        timestamp=base_time + timedelta(minutes=5),
    )

    repository.add(first)
    repository.add(second)
    sqlite_session.commit()

    assert repository.exists(first)
    assert repository.exists(second)
    assert repository.latest_timestamp() == second.played_at


def test_play_event_repository_latest_timestamp_empty(sqlite_session: Session) -> None:
    repository = SqlAlchemyPlayEventRepository(sqlite_session)

    assert repository.latest_timestamp() is None


def test_play_event_repository_exists_returns_false_for_missing_rows(
    sqlite_session: Session,
) -> None:
    repository = SqlAlchemyPlayEventRepository(sqlite_session)
    timestamp = datetime.now(tz=UTC)

    missing = _persist_event_graph(sqlite_session, "Missing", timestamp=timestamp)
    missing._user.id = uuid.uuid4()
    assert repository.exists(missing) is False


def test_library_item_repository_exists_checks_user_target_identity(
    sqlite_session: Session,
) -> None:
    repository = SqlAlchemyLibraryItemRepository(sqlite_session)
    user = User(display_name="Listener")
    artist = Artist(name="Burial")
    item = user.save_entity(artist)

    sqlite_session.add_all([user, artist])
    sqlite_session.commit()

    repository.add(item)
    sqlite_session.commit()

    assert repository.exists(
        user_id=user.id,
        target_type=item.target_type,
        target_id=item.target_id,
    )
    assert not repository.exists(
        user_id=user.id,
        target_type=item.target_type,
        target_id=uuid.uuid4(),
    )
