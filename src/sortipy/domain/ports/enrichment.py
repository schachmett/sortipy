"""Port definitions for MusicBrainz-style enrichment."""

from __future__ import annotations

from collections.abc import Callable

from sortipy.domain.entity_updates import ReleaseCandidate, ReleaseUpdate
from sortipy.domain.model import Artist, Recording, ReleaseSet

ReleaseUpdateFetcher = Callable[[ReleaseCandidate], ReleaseUpdate]

ReleaseCandidatesFromRecording = Callable[[Recording], list[ReleaseCandidate]]
ReleaseCandidatesFromReleaseSet = Callable[[ReleaseSet], list[ReleaseCandidate]]
ReleaseCandidatesFromArtist = Callable[[Artist], list[ReleaseCandidate]]
