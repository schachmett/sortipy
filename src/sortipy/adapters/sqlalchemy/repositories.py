"""Repository implementations backed by SQLAlchemy sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from sqlalchemy import select

from sortipy.domain.types import PlayEvent

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import InstrumentedAttribute, Session


class SqlAlchemyPlayEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entity: PlayEvent) -> None:
        self._prepare_event(entity)
        self.session.add(entity)

    def exists(self, timestamp: datetime) -> bool:
        # Ruff insists on keeping InstrumentedAttribute imports outside TYPE_CHECKING when
        # used in casts, even under `from __future__ import annotations`, so keep the
        # annotation stringified to avoid a runtime import here.
        played_at_column = cast("InstrumentedAttribute[datetime]", PlayEvent.played_at)
        stmt = select(PlayEvent).where(played_at_column == timestamp)
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def latest_timestamp(self) -> datetime | None:
        played_at_column = cast("InstrumentedAttribute[datetime]", PlayEvent.played_at)
        stmt = select(played_at_column).order_by(played_at_column.desc()).limit(1)
        return self.session.execute(stmt).scalar_one_or_none()

    def _prepare_event(self, event: PlayEvent) -> None:
        # Placeholder hook for canonical-entity deduplication once persistence for
        # the broader catalog is available (see ADR-0002/0003). For now, events are
        # stored verbatim and dedupe will be handled in a dedicated service.
        _ = event


if TYPE_CHECKING:
    from sortipy.domain.ports.persistence import PlayEventRepository

    _session_stub = cast("Session", object())
    _repo_check: PlayEventRepository = SqlAlchemyPlayEventRepository(_session_stub)
