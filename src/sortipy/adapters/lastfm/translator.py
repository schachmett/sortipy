"""Translate Last.fm payloads into domain entities."""

from __future__ import annotations

from datetime import UTC, datetime
from logging import getLogger

from sortipy.domain.types import (
    Artist,
    ArtistRole,
    ExternalNamespace,
    PlayEvent,
    Provider,
    Recording,
    RecordingArtist,
    Release,
    ReleaseSet,
    ReleaseSetArtist,
    Track,
)

from .schema import TrackPayload, TrackPayloadInput

log = getLogger(__name__)


def _ensure_track_payload(scrobble: TrackPayloadInput) -> TrackPayload:
    if isinstance(scrobble, TrackPayload):
        return scrobble
    return TrackPayload.model_validate(scrobble)


def parse_play_event(scrobble: TrackPayloadInput) -> PlayEvent:
    track_payload = _ensure_track_payload(scrobble)

    if track_payload.is_now_playing:
        played_at = datetime.now(UTC)
    elif track_payload.date is not None:
        played_at = datetime.fromtimestamp(track_payload.date.uts, tz=UTC)
    else:
        raise ValueError("Invalid scrobble")

    try:
        artist, release_set, _release, recording, track = _parse_entities(track_payload)
    except Exception:  # pragma: no cover
        log.exception("Error parsing play event")
        raise

    event = PlayEvent(
        played_at=played_at,
        source=Provider.LASTFM,
        recording=recording,
        track=track,
    )
    recording.play_events.append(event)
    track.play_events.append(event)

    if recording not in artist.recordings:
        artist.recordings.append(recording)
    if release_set not in artist.release_sets:
        artist.release_sets.append(release_set)

    return event


def _parse_entities(payload: TrackPayload) -> tuple[Artist, ReleaseSet, Release, Recording, Track]:
    artist = Artist(name=payload.artist.name)
    if payload.artist.mbid:
        artist.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, payload.artist.mbid)
    artist.sources.add(Provider.LASTFM)

    album_title = payload.album.title or payload.name
    release_set = ReleaseSet(title=album_title)
    release_set.sources.add(Provider.LASTFM)
    if payload.album.mbid:
        release_set.add_external_id(ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP, payload.album.mbid)

    release = Release(title=album_title, release_set=release_set)
    release.sources.add(Provider.LASTFM)
    if payload.album.mbid:
        release.add_external_id(ExternalNamespace.MUSICBRAINZ_RELEASE, payload.album.mbid)

    recording = Recording(title=payload.name)
    recording.sources.add(Provider.LASTFM)
    if payload.mbid:
        recording.add_external_id(ExternalNamespace.MUSICBRAINZ_RECORDING, payload.mbid)

    track = Track(release=release, recording=recording)
    track.sources.add(Provider.LASTFM)

    release_set.releases.append(release)
    release_set.artists.append(
        ReleaseSetArtist(release_set=release_set, artist=artist, role=ArtistRole.PRIMARY)
    )

    release.tracks.append(track)

    recording.tracks.append(track)
    recording.artists.append(
        RecordingArtist(recording=recording, artist=artist, role=ArtistRole.PRIMARY)
    )

    return artist, release_set, release, recording, track
