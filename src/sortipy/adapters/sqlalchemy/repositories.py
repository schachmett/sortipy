"""Repository implementations backed by SQLAlchemy sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select

from sortipy.adapters.sqlalchemy.merger import CanonicalEntityMerger
from sortipy.domain.types import PlayEvent

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

    from sortipy.domain.ports.persistence import PlayEventRepository


class SqlAlchemyPlayEventRepository:
    _merger: CanonicalEntityMerger

    def __init__(self, session: Session) -> None:
        self.session = session
        self._merger = CanonicalEntityMerger(session)

    def add(self, entity: PlayEvent) -> None:
        self._prepare_event(entity)
        self.session.add(entity)

    def exists(self, timestamp: datetime) -> bool:
        played_at_column = cast(Any, PlayEvent.played_at)
        stmt = select(PlayEvent).where(played_at_column == timestamp)
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def latest_timestamp(self) -> datetime | None:
        played_at_column = cast(Any, PlayEvent.played_at)
        stmt = select(played_at_column).order_by(played_at_column.desc()).limit(1)
        return self.session.execute(stmt).scalar_one_or_none()

    def _prepare_event(self, event: PlayEvent) -> None:
        recording = self._merger.merge_recording(event.recording)
        event.recording = recording

        if event.track is not None:
            track = event.track
            track.release = self._merger.merge_release(track.release)
            track.recording = recording
            event.track = self._merger.merge_track(track)

        if event.user is not None:
            event.user = self._merger.merge_user(event.user)


if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    _session_stub = cast(Session, ...)
    _repo_check: PlayEventRepository = SqlAlchemyPlayEventRepository(_session_stub)

__all__ = [
    "SqlAlchemyPlayEventRepository",
]
