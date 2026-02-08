"""MusicBrainz enrichment entry points."""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from sortipy.domain.model import ExternalNamespace

from .client import MusicBrainzAPIError, MusicBrainzClient
from .translator import (
    release_candidate_from_release,
    release_candidate_from_release_ref,
    translate_release,
)

if TYPE_CHECKING:
    from sortipy.config.musicbrainz import MusicBrainzConfig
    from sortipy.domain.entity_updates import ReleaseCandidate, ReleaseUpdate
    from sortipy.domain.model import Artist, Recording, ReleaseSet

    from .client import MusicBrainzLookupClient
    from .schema import MBRecording

log = getLogger(__name__)


def fetch_release_update(
    candidate: ReleaseCandidate,
    *,
    config: MusicBrainzConfig,
    client: MusicBrainzLookupClient | None = None,
) -> ReleaseUpdate:
    """Fetch a full release update graph from MusicBrainz."""

    active_client = client or MusicBrainzClient(config=config)
    payload = active_client.fetch_release(mbid=candidate.mbid)
    return translate_release(payload)


def fetch_release_candidates_from_recording(
    recording: Recording,
    *,
    config: MusicBrainzConfig,
    client: MusicBrainzLookupClient | None = None,
) -> list[ReleaseCandidate]:
    """Find release candidates for a recording via MusicBrainz."""

    active_client = client or MusicBrainzClient(config=config)
    payload = _recording_payload(active_client, recording)
    if payload is None:
        return []
    return [release_candidate_from_release(release) for release in payload.releases]


def fetch_release_candidates_from_release_set(
    release_set: ReleaseSet,
    *,
    config: MusicBrainzConfig,
    client: MusicBrainzLookupClient | None = None,
) -> list[ReleaseCandidate]:
    """Find release candidates for a release set via MusicBrainz."""

    mbid = _release_set_mbid(release_set)
    if mbid is None:
        return []
    active_client = client or MusicBrainzClient(config=config)
    results = active_client.browse_releases_by_release_group(release_group_mbid=mbid)
    return [release_candidate_from_release_ref(release) for release in results.releases]


def fetch_release_candidates_from_artist(
    artist: Artist,
    *,
    config: MusicBrainzConfig,
    client: MusicBrainzLookupClient | None = None,
) -> list[ReleaseCandidate]:
    """Find release candidates for an artist via MusicBrainz."""

    mbid = _artist_mbid(artist)
    if mbid is None:
        return []
    active_client = client or MusicBrainzClient(config=config)
    results = active_client.browse_releases_by_artist(artist_mbid=mbid)
    return [release_candidate_from_release_ref(release) for release in results.releases]


def _recording_payload(
    client: MusicBrainzLookupClient,
    recording: Recording,
) -> MBRecording | None:
    mbid = _recording_mbid(recording)
    try:
        payload = (
            client.fetch_recording(mbid=mbid)
            if mbid is not None
            else _search_recording(client, recording)
        )
    except MusicBrainzAPIError as exc:
        log.warning("MusicBrainz fetch failed for recording %s: %s", recording.id, exc)
        return None
    return payload


def _recording_mbid(recording: Recording) -> str | None:
    entry = recording.external_ids_by_namespace.get(ExternalNamespace.MUSICBRAINZ_RECORDING)
    if entry is None:
        return None
    return entry.value


def _release_set_mbid(release_set: ReleaseSet) -> str | None:
    entry = release_set.external_ids_by_namespace.get(ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP)
    if entry is None:
        return None
    return entry.value


def _artist_mbid(artist: Artist) -> str | None:
    entry = artist.external_ids_by_namespace.get(ExternalNamespace.MUSICBRAINZ_ARTIST)
    if entry is None:
        return None
    return entry.value


def _search_recording(
    client: MusicBrainzLookupClient,
    recording: Recording,
) -> MBRecording | None:
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
