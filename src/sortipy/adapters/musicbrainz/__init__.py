"""MusicBrainz reconciliation adapter."""

from __future__ import annotations

from .candidates import (
    MusicBrainzReleaseCandidate,
    MusicBrainzReleaseCandidatesFromArtist,
    MusicBrainzReleaseCandidatesFromRecording,
    MusicBrainzReleaseCandidatesFromRelease,
    MusicBrainzReleaseCandidatesFromReleaseSet,
    MusicBrainzReleaseGraphFetcher,
    MusicBrainzReleaseGraphFetchResult,
    MusicBrainzReleaseSelectionPolicy,
    resolve_release_candidate,
)
from .fetcher import (
    fetch_release_candidates_from_artist,
    fetch_release_candidates_from_recording,
    fetch_release_candidates_from_release,
    fetch_release_candidates_from_release_set,
    fetch_release_graph,
)

__all__ = [
    "MusicBrainzReleaseCandidate",
    "MusicBrainzReleaseCandidatesFromArtist",
    "MusicBrainzReleaseCandidatesFromRecording",
    "MusicBrainzReleaseCandidatesFromRelease",
    "MusicBrainzReleaseCandidatesFromReleaseSet",
    "MusicBrainzReleaseGraphFetchResult",
    "MusicBrainzReleaseGraphFetcher",
    "MusicBrainzReleaseSelectionPolicy",
    "fetch_release_candidates_from_artist",
    "fetch_release_candidates_from_recording",
    "fetch_release_candidates_from_release",
    "fetch_release_candidates_from_release_set",
    "fetch_release_graph",
    "resolve_release_candidate",
]
