"""Translate Last.fm payloads into domain entities.

This module constructs a graph using `sortipy.domain.model` commands.
"""

from __future__ import annotations

from datetime import UTC, datetime
from logging import getLogger
from typing import TYPE_CHECKING

from sortipy.domain.model import (
    Artist,
    ArtistRole,
    ExternalNamespace,
    Provider,
    Recording,
    ReleaseSet,
)

from .schema import TrackPayload

if TYPE_CHECKING:
    from sortipy.domain.model import (
        PlayEvent,
        Release,
        ReleaseTrack,
        User,
    )

    from .schema import TrackPayloadInput


log = getLogger(__name__)


def _ensure_track_payload(scrobble: TrackPayloadInput) -> TrackPayload:
    if isinstance(scrobble, TrackPayload):
        return scrobble
    return TrackPayload.model_validate(scrobble)


def _resolve_played_at(payload: TrackPayload, played_at: datetime | None) -> datetime:
    if played_at is not None:
        return played_at
    if payload.is_now_playing:
        return datetime.now(UTC)
    if payload.date is not None:
        return datetime.fromtimestamp(payload.date.uts, tz=UTC)
    raise ValueError("Invalid scrobble")


def parse_play_event(
    scrobble: TrackPayloadInput,
    *,
    played_at: datetime | None = None,
    user: User,
) -> PlayEvent:
    """Return a domain.model PlayEvent.

    The caller may pass a shared `user` instance to keep ownership stable across a batch.
    """

    payload = _ensure_track_payload(scrobble)
    when = _resolve_played_at(payload, played_at)

    if not payload.album.title:
        log.warning(
            "No album title given for Recording %s by Artist %s", payload.name, payload.artist.name
        )

    active_user = user
    artist = _build_artist(payload)
    release_set, release = _build_release_set_and_release(payload)
    recording = _build_recording(payload)
    track = _build_track(release=release, recording=recording)

    release_set.add_artist(artist, role=ArtistRole.PRIMARY)
    recording.add_artist(artist, role=ArtistRole.PRIMARY)

    return active_user.log_play(
        played_at=when, source=Provider.LASTFM, recording=recording, track=track
    )


def _build_artist(payload: TrackPayload) -> Artist:
    artist = Artist(name=payload.artist.name)
    artist.add_source(Provider.LASTFM)
    if payload.artist.mbid:
        artist.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, payload.artist.mbid)
    if payload.artist.url:
        artist.add_external_id(ExternalNamespace.LASTFM_ARTIST, payload.artist.url)
    return artist


def _build_release_set_and_release(payload: TrackPayload) -> tuple[ReleaseSet, Release]:
    album_title = payload.album.title or payload.name
    release_set = ReleaseSet(title=album_title)
    release_set.add_source(Provider.LASTFM)

    release = release_set.create_release(title=album_title)
    release.add_source(Provider.LASTFM)
    if payload.album.mbid:
        release.add_external_id(ExternalNamespace.MUSICBRAINZ_RELEASE, payload.album.mbid)
    return release_set, release


def _build_recording(payload: TrackPayload) -> Recording:
    recording = Recording(title=payload.name)
    recording.add_source(Provider.LASTFM)
    if payload.mbid:
        recording.add_external_id(ExternalNamespace.MUSICBRAINZ_RECORDING, payload.mbid)
    if payload.url:
        recording.add_external_id(ExternalNamespace.LASTFM_RECORDING, payload.url)
    return recording


def _build_track(*, release: Release, recording: Recording) -> ReleaseTrack:
    track = release.add_track(recording)
    track.add_source(Provider.LASTFM)
    return track
