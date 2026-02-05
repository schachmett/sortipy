"""Domain services for enrichment workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from sortipy.domain.model import Artist, ExternalNamespace

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sortipy.domain.model import Provider, Recording
    from sortipy.domain.ports.enrichment import (
        ArtistCreditUpdate,
        RecordingEnrichmentFetcher,
        RecordingEnrichmentUpdate,
    )


@dataclass(slots=True)
class RecordingEnrichmentResult:
    candidates: int
    updates: int
    applied: int


class RecordingEnrichmentPolicy(Protocol):
    def accept(self, recording: Recording, update: RecordingEnrichmentUpdate) -> bool: ...


def enrich_recordings(
    recordings: Iterable[Recording],
    *,
    fetcher: RecordingEnrichmentFetcher,
    policy: RecordingEnrichmentPolicy | None = None,
) -> list[RecordingEnrichmentUpdate]:
    """Fetch enrichment updates for the given recordings."""

    recording_list = list(recordings)
    updates = list(fetcher(recording_list))
    if policy is None:
        return updates
    recording_by_id = {recording.id: recording for recording in recording_list}
    accepted: list[RecordingEnrichmentUpdate] = []
    for update in updates:
        recording = recording_by_id.get(update.recording_id)
        if recording is None:
            continue
        if policy.accept(recording, update):
            accepted.append(update)
    return accepted


def apply_recording_updates(
    recordings: Iterable[Recording],
    updates: Iterable[RecordingEnrichmentUpdate],
    *,
    policy: RecordingEnrichmentPolicy | None = None,
) -> list[Recording]:
    """Apply enrichment updates to the provided recordings in-place."""

    recording_by_id = {recording.id: recording for recording in recordings}
    updated: list[Recording] = []

    for update in updates:
        recording = recording_by_id.get(update.recording_id)
        if recording is None:
            continue
        if policy is not None and not policy.accept(recording, update):
            continue
        _apply_recording_update(recording, update)
        updated.append(recording)

    return updated


def select_recording_candidates(recordings: Iterable[Recording]) -> list[Recording]:
    """Select recordings that likely benefit from MusicBrainz enrichment."""

    candidates: list[Recording] = []
    for recording in recordings:
        if _needs_recording_mbid(recording):
            candidates.append(recording)
            continue
        if _needs_isrc(recording):
            candidates.append(recording)
            continue
        if _needs_artist_mbid(recording):
            candidates.append(recording)
    return candidates


def _apply_recording_update(
    recording: Recording,
    update: RecordingEnrichmentUpdate,
) -> None:
    if update.title is not None:
        recording.title = update.title
    if update.disambiguation is not None:
        recording.disambiguation = update.disambiguation
    if update.duration_ms is not None:
        recording.duration_ms = update.duration_ms

    _apply_sources(recording, update.sources)
    _apply_recording_ids(recording, update)
    _apply_isrcs(recording, update)
    _apply_artist_credits(recording, update.artist_credits)


def _apply_sources(recording: Recording, sources: set[Provider]) -> None:
    for source in sources:
        recording.add_source(source)


def _apply_recording_ids(recording: Recording, update: RecordingEnrichmentUpdate) -> None:
    if update.mbid is None:
        return
    recording.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RECORDING,
        update.mbid,
        replace=True,
    )


def _apply_isrcs(recording: Recording, update: RecordingEnrichmentUpdate) -> None:
    for isrc in update.isrcs:
        recording.add_external_id(ExternalNamespace.RECORDING_ISRC, str(isrc))


def _apply_artist_credits(
    recording: Recording,
    credits_: list[ArtistCreditUpdate] | None,
) -> None:
    if credits_ is None:
        return

    for credit in credits_:
        artist = _resolve_artist(recording, credit)
        if artist is None:
            artist = Artist(name=credit.name)
            if credit.artist_mbid:
                artist.add_external_id(
                    ExternalNamespace.MUSICBRAINZ_ARTIST,
                    credit.artist_mbid,
                    replace=True,
                )
            recording.add_artist(artist, role=credit.role, credit_order=credit.credit_order)
        contribution = next(
            (
                c
                for c in recording.contributions
                if c.artist is artist and c.credit_order == credit.credit_order
            ),
            None,
        )
        if contribution is None:
            contribution = recording.add_artist(
                artist,
                role=credit.role,
                credit_order=credit.credit_order,
                credited_as=credit.credited_as,
            )
        contribution.role = credit.role
        contribution.credit_order = credit.credit_order
        contribution.credited_as = credit.credited_as


def _resolve_artist(
    recording: Recording,
    credit: ArtistCreditUpdate,
) -> Artist | None:
    if credit.artist_mbid:
        for artist in recording.artists:
            external = artist.external_ids_by_namespace.get(ExternalNamespace.MUSICBRAINZ_ARTIST)
            if external and external.value == credit.artist_mbid:
                return artist
    for artist in recording.artists:
        if artist.name == credit.name:
            if credit.artist_mbid:
                artist.add_external_id(
                    ExternalNamespace.MUSICBRAINZ_ARTIST,
                    credit.artist_mbid,
                    replace=True,
                )
            return artist
    return None


def _needs_recording_mbid(recording: Recording) -> bool:
    return ExternalNamespace.MUSICBRAINZ_RECORDING not in recording.external_ids_by_namespace


def _needs_isrc(recording: Recording) -> bool:
    return ExternalNamespace.RECORDING_ISRC not in recording.external_ids_by_namespace


def _needs_artist_mbid(recording: Recording) -> bool:
    for artist in recording.artists:
        if ExternalNamespace.MUSICBRAINZ_ARTIST not in artist.external_ids_by_namespace:
            return True
    return False
