"""Domain port definitions for adapters."""

from __future__ import annotations

from sortipy.domain.entity_updates import (
    ArtistUpdate,
    ContributionUpdate,
    EnrichmentMetadata,
    ExternalIdUpdate,
    LabelUpdate,
    RecordingUpdate,
    ReleaseCandidate,
    ReleaseSetUpdate,
    ReleaseTrackUpdate,
    ReleaseUpdate,
)

from .enrichment import (
    ReleaseCandidatesFromArtist,
    ReleaseCandidatesFromRecording,
    ReleaseCandidatesFromReleaseSet,
    ReleaseUpdateFetcher,
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
    "ArtistUpdate",
    "CanonicalEntityRepository",
    "CatalogRepositories",
    "ContributionUpdate",
    "EnrichmentMetadata",
    "ExternalIdUpdate",
    "LabelRepository",
    "LabelUpdate",
    "LibraryItemFetchResult",
    "LibraryItemFetcher",
    "LibraryItemRepository",
    "PlayEventFetchResult",
    "PlayEventFetcher",
    "PlayEventRepository",
    "RecordingRepository",
    "RecordingUpdate",
    "ReleaseCandidate",
    "ReleaseCandidatesFromArtist",
    "ReleaseCandidatesFromRecording",
    "ReleaseCandidatesFromReleaseSet",
    "ReleaseRepository",
    "ReleaseSetRepository",
    "ReleaseSetUpdate",
    "ReleaseTrackUpdate",
    "ReleaseUpdate",
    "ReleaseUpdateFetcher",
    "Repository",
    "RepositoryCollection",
    "UnitOfWork",
    "UserRepository",
]
