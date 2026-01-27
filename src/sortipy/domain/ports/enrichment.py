"""Port definitions for MusicBrainz-style enrichment."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sortipy.domain.model import Recording

if TYPE_CHECKING:
    from uuid import UUID

    from sortipy.domain.model import ArtistRole, Isrc, Provider


@dataclass(slots=True)
class ArtistCreditUpdate:
    """Artist credit update derived from enrichment."""

    artist_mbid: str | None
    name: str
    role: ArtistRole
    credit_order: int
    credited_as: str | None = None
    join_phrase: str | None = None


@dataclass(slots=True)
class RecordingEnrichmentUpdate:
    """Enrichment update for a recording."""

    recording_id: UUID
    mbid: str | None = None
    title: str | None = None
    disambiguation: str | None = None
    duration_ms: int | None = None
    isrcs: set[Isrc] = field(default_factory=set["Isrc"])
    artist_credits: list[ArtistCreditUpdate] | None = None
    confidence: float = 0.0
    sources: set[Provider] = field(default_factory=set["Provider"])


RecordingEnrichmentFetcher = Callable[
    [Iterable[Recording]],
    Iterable[RecordingEnrichmentUpdate],
]
