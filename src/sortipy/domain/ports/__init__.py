"""Domain port definitions for adapters."""

from __future__ import annotations

from .fetching import PlayEventFetcher, PlayEventFetchResult
from .persistence import (
    ArtistRepository,
    PlayEventRepository,
    RecordingRepository,
    ReleaseRepository,
    ReleaseSetRepository,
    Repository,
)
from .unit_of_work import (
    PlayEventRepositories,
    PlayEventUnitOfWork,
    RepositoryCollection,
    UnitOfWork,
)

__all__ = [
    "ArtistRepository",
    "PlayEventFetchResult",
    "PlayEventFetcher",
    "PlayEventRepositories",
    "PlayEventRepository",
    "PlayEventUnitOfWork",
    "RecordingRepository",
    "ReleaseRepository",
    "ReleaseSetRepository",
    "Repository",
    "RepositoryCollection",
    "UnitOfWork",
]
