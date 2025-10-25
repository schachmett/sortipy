"""Ports for persisting domain aggregates."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from sortipy.domain.types import PlayEvent

if TYPE_CHECKING:
    from datetime import datetime


@runtime_checkable
class Repository[TEntity](Protocol):
    """Minimal repository contract for a persistent aggregate store."""

    def add(self, entity: TEntity) -> None: ...


@runtime_checkable
class PlayEventRepository(Repository[PlayEvent], Protocol):
    """Persistence contract for play events."""

    def exists(self, timestamp: datetime) -> bool: ...

    def latest_timestamp(self) -> datetime | None: ...


__all__ = ["PlayEventRepository", "Repository"]
