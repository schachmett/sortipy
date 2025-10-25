"""Domain port definitions for adapters."""

from __future__ import annotations

from .fetching import PlayEventFetcher, PlayEventFetchResult
from .persistence import PlayEventRepository, Repository
from .unit_of_work import (
    PlayEventRepositories,
    PlayEventUnitOfWork,
    RepositoryCollection,
    UnitOfWork,
)

__all__ = [
    "PlayEventFetchResult",
    "PlayEventFetcher",
    "PlayEventRepositories",
    "PlayEventRepository",
    "PlayEventUnitOfWork",
    "Repository",
    "RepositoryCollection",
    "UnitOfWork",
]
