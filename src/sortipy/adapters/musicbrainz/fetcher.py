"""MusicBrainz enrichment entry points."""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING, Protocol

from sortipy.domain.model import ExternalNamespace

from .client import MusicBrainzAPIError, MusicBrainzClient
from .translator import translate_recording

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sortipy.config.musicbrainz import MusicBrainzConfig
    from sortipy.domain.model import Recording
    from sortipy.domain.ports.enrichment import RecordingEnrichmentUpdate

    from .schema import MusicBrainzRecording, MusicBrainzRecordingSearch

log = getLogger(__name__)


class RecordingLookupClient(Protocol):
    def fetch_recording(
        self, *, mbid: str, inc: tuple[str, ...] | None = None
    ) -> MusicBrainzRecording: ...

    def search_recordings(
        self,
        *,
        query: str,
        limit: int = 1,
        offset: int = 0,
        inc: tuple[str, ...] | None = None,
    ) -> MusicBrainzRecordingSearch: ...


def enrich_recordings(
    recordings: Iterable[Recording],
    *,
    config: MusicBrainzConfig,
    client: RecordingLookupClient | None = None,
) -> list[RecordingEnrichmentUpdate]:
    """Enrich recordings with MusicBrainz data."""

    active_client = client or MusicBrainzClient(config=config)
    updates: list[RecordingEnrichmentUpdate] = []

    for recording in recordings:
        mbid = _recording_mbid(recording)
        try:
            payload = (
                active_client.fetch_recording(mbid=mbid)
                if mbid is not None
                else _search_recording(active_client, recording)
            )
        except MusicBrainzAPIError as exc:
            log.warning("MusicBrainz fetch failed for recording %s: %s", recording.id, exc)
            continue
        if payload is None:
            continue
        updates.append(translate_recording(payload, recording_id=recording.id))

    return updates


def _recording_mbid(recording: Recording) -> str | None:
    entry = recording.external_ids_by_namespace.get(ExternalNamespace.MUSICBRAINZ_RECORDING)
    if entry is None:
        return None
    return entry.value


def _search_recording(
    client: RecordingLookupClient,
    recording: Recording,
) -> MusicBrainzRecording | None:
    query = _search_query(recording)
    if query is None:
        return None
    results = client.search_recordings(query=query, limit=1)
    if not results.recordings:
        log.info("MusicBrainz search returned no results for recording %s", recording.id)
        return None
    return results.recordings[0]


def _search_query(recording: Recording) -> str | None:
    title = recording.title.strip()
    if not title:
        return None
    artists = recording.artists
    if not artists:
        return f'recording:"{title}"'
    artist = artists[0].name
    return f'recording:"{title}" AND artist:"{artist}"'
