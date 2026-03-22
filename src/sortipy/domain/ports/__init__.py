"""Domain port definitions for adapters."""

from __future__ import annotations

from .enrichment import (
    ReleaseCandidate,
    ReleaseCandidatesFromArtist,
    ReleaseCandidatesFromRecording,
    ReleaseCandidatesFromReleaseSet,
    ReleaseGraphFetcher,
)
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
    NormalizationSidecarRepository,
    PlayEventRepository,
    PriorityKeysData,
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
    "NormalizationSidecarRepository",
    "PlayEventFetchResult",
    "PlayEventFetcher",
    "PlayEventRepository",
    "PriorityKeysData",
    "RecordingRepository",
    "ReleaseCandidate",
    "ReleaseCandidatesFromArtist",
    "ReleaseCandidatesFromRecording",
    "ReleaseCandidatesFromReleaseSet",
    "ReleaseGraphFetcher",
    "ReleaseRepository",
    "ReleaseSetRepository",
    "Repository",
    "RepositoryCollection",
    "UnitOfWork",
    "UserRepository",
]
