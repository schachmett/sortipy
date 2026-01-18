"""Domain port definitions for adapters."""

from __future__ import annotations

from .fetching import (
    LibraryItemFetcher,
    LibraryItemFetchResult,
    PlayEventFetcher,
    PlayEventFetchResult,
)
from .persistence import (
    ArtistRepository,
    CanonicalEntityRepository,
    LabelRepository,
    LibraryItemRepository,
    PlayEventRepository,
    RecordingRepository,
    ReleaseRepository,
    ReleaseSetRepository,
    Repository,
    UserRepository,
)
from .unit_of_work import (
    CatalogRepositories,
    RepositoryCollection,
    UnitOfWork,
)

__all__ = [
    "ArtistRepository",
    "CanonicalEntityRepository",
    "CatalogRepositories",
    "LabelRepository",
    "LibraryItemFetchResult",
    "LibraryItemFetcher",
    "LibraryItemRepository",
    "PlayEventFetchResult",
    "PlayEventFetcher",
    "PlayEventRepository",
    "RecordingRepository",
    "ReleaseRepository",
    "ReleaseSetRepository",
    "Repository",
    "RepositoryCollection",
    "UnitOfWork",
    "UserRepository",
]
