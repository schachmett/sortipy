"""Domain entity update subsystem."""

from __future__ import annotations

from .apply import apply_release_update
from .dto import (
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
from .resolve import ReleaseSelectionPolicy, resolve_release_candidate

__all__ = [
    "ArtistUpdate",
    "ContributionUpdate",
    "EnrichmentMetadata",
    "ExternalIdUpdate",
    "LabelUpdate",
    "RecordingUpdate",
    "ReleaseCandidate",
    "ReleaseSelectionPolicy",
    "ReleaseSetUpdate",
    "ReleaseTrackUpdate",
    "ReleaseUpdate",
    "apply_release_update",
    "resolve_release_candidate",
]
