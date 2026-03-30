"""MusicBrainz reconciliation entry points."""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from sortipy.domain.model import ExternalNamespace

from .candidates import (
    MusicBrainzReleaseGraphFetchResult,
    release_candidate_from_release,
    release_candidate_from_release_ref,
)
from .client import MusicBrainzAPIError, MusicBrainzClient, MusicBrainzNotFoundError
from .translator import (
    parse_partial_date,
    release_media_formats,
    release_packaging,
    release_status,
    release_track_count,
    translate_release,
)

if TYPE_CHECKING:
    from sortipy.config.musicbrainz import MusicBrainzConfig
    from sortipy.domain.model import Artist, Recording, Release, ReleaseSet

    from .candidates import MusicBrainzReleaseCandidate
    from .client import MusicBrainzLookupClient
    from .schema import MBRecording

log = getLogger(__name__)
RECORDING_SEARCH_LIMIT = 5


def fetch_release_graph(
    candidate: MusicBrainzReleaseCandidate,
    *,
    config: MusicBrainzConfig,
    client: MusicBrainzLookupClient | None = None,
) -> MusicBrainzReleaseGraphFetchResult:
    """Fetch a full release aggregate graph from MusicBrainz."""

    active_client = client or MusicBrainzClient(config=config)
    payload = active_client.fetch_release(mbid=candidate.mbid)
    return MusicBrainzReleaseGraphFetchResult(
        release=translate_release(payload),
        requested_mbid=candidate.mbid,
        resolved_mbid=payload.id,
        redirected=payload.id != candidate.mbid,
    )


def fetch_release_candidates_from_recording(
    recording: Recording,
    *,
    config: MusicBrainzConfig,
    client: MusicBrainzLookupClient | None = None,
) -> list[MusicBrainzReleaseCandidate]:
    """Find release candidates for a recording via MusicBrainz."""

    active_client = client or MusicBrainzClient(config=config)
    payloads = _recording_payloads(active_client, recording)
    if not payloads:
        return []
    candidates_by_mbid: dict[str, MusicBrainzReleaseCandidate] = {}
    for payload in payloads:
        for release in payload.releases:
            candidates_by_mbid.setdefault(
                release.id,
                release_candidate_from_release(
                    release,
                    release_date=parse_partial_date(release.date),
                    status=release_status(release.status),
                    packaging=release_packaging(release.packaging),
                    track_count=release_track_count(release),
                    media_formats=release_media_formats(release),
                ),
            )

    return list(candidates_by_mbid.values())


def fetch_release_candidates_from_release(
    release: Release,
    *,
    config: MusicBrainzConfig,
    client: MusicBrainzLookupClient | None = None,
) -> list[MusicBrainzReleaseCandidate]:
    """Find release candidates for a release via MusicBrainz release search."""

    query = _release_search_query(release)
    if query is None:
        return []
    active_client = client or MusicBrainzClient(config=config)
    results = active_client.search_releases(query=query, limit=5)
    if not results.releases:
        log.info("MusicBrainz search returned no results for release %s", release.id)
        return []
    return [
        release_candidate_from_release_ref(
            candidate,
            release_date=parse_partial_date(candidate.date),
            status=release_status(candidate.status),
            packaging=release_packaging(candidate.packaging),
        )
        for candidate in results.releases
    ]


def fetch_release_candidates_from_release_set(
    release_set: ReleaseSet,
    *,
    config: MusicBrainzConfig,
    client: MusicBrainzLookupClient | None = None,
) -> list[MusicBrainzReleaseCandidate]:
    """Find release candidates for a release set via MusicBrainz."""

    mbid = _release_set_mbid(release_set)
    if mbid is None:
        return []
    active_client = client or MusicBrainzClient(config=config)
    results = active_client.browse_releases_by_release_group(release_group_mbid=mbid)
    return [
        release_candidate_from_release_ref(
            release,
            release_date=parse_partial_date(release.date),
            status=release_status(release.status),
            packaging=release_packaging(release.packaging),
        )
        for release in results.releases
    ]


def fetch_release_candidates_from_artist(
    artist: Artist,
    *,
    config: MusicBrainzConfig,
    client: MusicBrainzLookupClient | None = None,
) -> list[MusicBrainzReleaseCandidate]:
    """Find release candidates for an artist via MusicBrainz."""

    mbid = _artist_mbid(artist)
    if mbid is None:
        return []
    active_client = client or MusicBrainzClient(config=config)
    results = active_client.browse_releases_by_artist(artist_mbid=mbid)
    return [
        release_candidate_from_release_ref(
            release,
            release_date=parse_partial_date(release.date),
            status=release_status(release.status),
            packaging=release_packaging(release.packaging),
        )
        for release in results.releases
    ]


def _recording_payloads(
    client: MusicBrainzLookupClient,
    recording: Recording,
) -> list[MBRecording]:
    mbid = _recording_mbid(recording)
    try:
        if mbid is not None:
            try:
                return [client.fetch_recording(mbid=mbid)]
            except MusicBrainzNotFoundError:
                log.info(
                    "MusicBrainz recording %s not found for recording %s; falling back to search",
                    mbid,
                    recording.id,
                )
                return _search_recordings(client, recording)
        payloads = _search_recordings(client, recording)
    except MusicBrainzAPIError as exc:
        log.warning("MusicBrainz fetch failed for recording %s: %s", recording.id, exc)
        return []
    return payloads


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


def _search_recordings(
    client: MusicBrainzLookupClient,
    recording: Recording,
) -> list[MBRecording]:
    query = _search_query(recording)
    if query is None:
        return []
    results = client.search_recordings(query=query, limit=RECORDING_SEARCH_LIMIT)
    if not results.recordings:
        log.info("MusicBrainz search returned no results for recording %s", recording.id)
        return []
    return results.recordings


def _search_query(recording: Recording) -> str | None:
    title = recording.title.strip()
    if not title:
        return None
    artists = recording.artists
    if not artists:
        return f'recording:"{title}"'
    artist = artists[0].name
    return f'recording:"{title}" AND artist:"{artist}"'


def _release_search_query(release: Release) -> str | None:
    title = release.title.strip()
    if not title:
        return None
    artist_names = _release_artist_names(release)
    if not artist_names:
        return f'release:"{title}"'
    return f'release:"{title}" AND artist:"{artist_names[0]}"'


def _release_artist_names(release: Release) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for recording in release.recordings:
        for artist in recording.artists:
            if artist.name in seen:
                continue
            seen.add(artist.name)
            names.append(artist.name)
    return names
