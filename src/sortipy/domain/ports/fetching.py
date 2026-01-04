"""Ports for fetching external domain data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from sortipy.domain.model import LibraryItem, PlayEvent, User


@dataclass(slots=True)
class PlayEventFetchResult:
    """Batch of play events fetched from an external provider."""

    events: Iterable[PlayEvent]
    now_playing: PlayEvent | None = None


@runtime_checkable
class PlayEventFetcher(Protocol):
    """Callable port for retrieving play events from an external provider."""

    def __call__(
        self,
        *,
        batch_size: int = 200,
        since: datetime | None = None,
        until: datetime | None = None,
        max_events: int | None = None,
    ) -> PlayEventFetchResult: ...


@dataclass(slots=True)
class LibraryItemFetchResult:
    library_items: Iterable[LibraryItem]


@runtime_checkable
class LibraryItemFetcher(Protocol):
    """Callable port for retrieving library items from an external provider."""

    def __call__(
        self,
        *,
        user: User,
        batch_size: int = 50,
        max_tracks: int | None = None,
        max_albums: int | None = None,
        max_artists: int | None = None,
    ) -> LibraryItemFetchResult: ...
