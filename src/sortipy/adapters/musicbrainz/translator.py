"""Translate MusicBrainz payloads into enrichment updates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sortipy.domain.model import ArtistRole, Provider
from sortipy.domain.ports.enrichment import ArtistCreditUpdate, RecordingEnrichmentUpdate

if TYPE_CHECKING:
    from uuid import UUID

    from .schema import MusicBrainzArtistCredit, MusicBrainzRecording


def translate_recording(
    recording: MusicBrainzRecording,
    *,
    recording_id: UUID,
) -> RecordingEnrichmentUpdate:
    return RecordingEnrichmentUpdate(
        recording_id=recording_id,
        mbid=recording.id,
        title=recording.title,
        disambiguation=recording.disambiguation or None,
        duration_ms=recording.length,
        isrcs=set(recording.isrcs),
        artist_credits=_build_artist_credits(recording.artist_credit),
        confidence=1.0,
        sources={Provider.MUSICBRAINZ},
    )


def _build_artist_credits(
    credits_: list[MusicBrainzArtistCredit],
) -> list[ArtistCreditUpdate]:
    updates: list[ArtistCreditUpdate] = []
    prev_join: str | None = None

    for index, credit in enumerate(credits_):
        role = _role_for_credit(index=index, prev_join_phrase=prev_join)
        credited_as = _credited_as(credit)
        updates.append(
            ArtistCreditUpdate(
                artist_mbid=credit.artist.id,
                name=credit.artist.name,
                role=role,
                credit_order=index,
                credited_as=credited_as,
                join_phrase=credit.join_phrase,
            )
        )
        prev_join = credit.join_phrase

    return updates


def _role_for_credit(*, index: int, prev_join_phrase: str | None) -> ArtistRole:
    if index == 0:
        return ArtistRole.PRIMARY
    if _is_featuring(prev_join_phrase):
        return ArtistRole.FEATURED
    return ArtistRole.UNKNOWN


def _credited_as(credit: MusicBrainzArtistCredit) -> str | None:
    if credit.name and credit.name != credit.artist.name:
        return credit.name
    return None


def _is_featuring(join_phrase: str | None) -> bool:
    if join_phrase is None:
        return False
    lowered = join_phrase.lower()
    return "feat" in lowered or "ft." in lowered
