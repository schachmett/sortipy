"""Port definitions for MusicBrainz-style enrichment."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sortipy.domain.model import Artist, Recording, Release, ReleaseSet

if TYPE_CHECKING:
    from sortipy.domain.model import (
        CountryCode,
        Mbid,
        PartialDate,
        ReleasePackaging,
        ReleaseStatus,
    )


def _new_strings() -> list[str]:
    return []


@dataclass(slots=True)
class ReleaseCandidate:
    """Candidate release summary for enrichment selection."""

    mbid: Mbid
    title: str | None = None
    release_date: PartialDate | None = None
    status: ReleaseStatus | None = None
    packaging: ReleasePackaging | None = None
    country: CountryCode | None = None
    release_set_mbid: Mbid | None = None
    artist_names: list[str] = field(default_factory=_new_strings)
    track_count: int | None = None
    media_formats: list[str] = field(default_factory=_new_strings)


ReleaseGraphFetcher = Callable[[ReleaseCandidate], Release]

ReleaseCandidatesFromRecording = Callable[[Recording], list[ReleaseCandidate]]
ReleaseCandidatesFromReleaseSet = Callable[[ReleaseSet], list[ReleaseCandidate]]
ReleaseCandidatesFromArtist = Callable[[Artist], list[ReleaseCandidate]]
