"""Repository implementations backed by SQLAlchemy sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar, cast

from sqlalchemy import select

from sortipy.adapters.sqlalchemy.merger import CanonicalEntityMerger
from sortipy.common.repository import Repository
from sortipy.domain.data_integration import PlayEventRepository
from sortipy.domain.types import PlayEvent

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

T = TypeVar("T")


class SQLAlchemyRepository(Repository[T]):
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, item: T) -> None:
        self.session.add(item)

    def remove(self, item: T) -> None:
        self.session.delete(item)

    def update(self, item: T) -> None:
        self.session.merge(item)


class SqlAlchemyPlayEventRepository(PlayEventRepository):
    _merger: CanonicalEntityMerger

    def __init__(self, session: Session) -> None:
        self.session = session
        self._merger = CanonicalEntityMerger(session)

    def add(self, event: PlayEvent) -> None:
        self._prepare_event(event)
        self.session.add(event)

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


__all__ = [
    "SQLAlchemyRepository",
    "SqlAlchemyPlayEventRepository",
]
