# ruff: noqa: I001

"""Translate Last.fm payloads into domain entities.

Note: the rest of the system still persists and ingests `sortipy.domain.types` graphs.
This module already constructs the graph using `sortipy.domain.model` commands, then
converts to legacy entities at the boundary to keep the migration incremental.
"""

from __future__ import annotations

from datetime import UTC, datetime
from logging import getLogger
from typing import TYPE_CHECKING, Protocol

from sortipy.domain.types import (
    Artist as LegacyArtist,
    ArtistRole as LegacyArtistRole,
    PlayEvent as LegacyPlayEvent,
    Provider as LegacyProvider,
    Recording as LegacyRecording,
    RecordingArtist as LegacyRecordingArtist,
    Release as LegacyRelease,
    ReleaseSet as LegacyReleaseSet,
    ReleaseSetArtist as LegacyReleaseSetArtist,
    Track as LegacyTrack,
)

from sortipy.domain.model.enums import ArtistRole, ExternalNamespace, Provider
from sortipy.domain.model.external_ids import ExternalIdCollection
from sortipy.domain.model.music import Artist, Recording, Release, ReleaseSet
from sortipy.domain.model.provenance import Provenanced
from sortipy.domain.model.user import PlayEvent as ModelPlayEvent, User

from .schema import TrackPayload, TrackPayloadInput

if TYPE_CHECKING:
    from sortipy.domain.model.associations import ReleaseTrack


log = getLogger(__name__)


class _LegacyExternallyIdentifiable(Protocol):
    def add_external_id(
        self,
        namespace: str,
        value: str,
        *,
        provider: LegacyProvider | None = None,
        replace: bool = False,
    ) -> None: ...


class _LegacySourced(Protocol):
    sources: set[LegacyProvider]


class _ModelMetadata(ExternalIdCollection, Provenanced, Protocol): ...


def _ensure_track_payload(scrobble: TrackPayloadInput) -> TrackPayload:
    if isinstance(scrobble, TrackPayload):
        return scrobble
    return TrackPayload.model_validate(scrobble)


def parse_play_event(scrobble: TrackPayloadInput) -> LegacyPlayEvent:
    try:
        model_event = parse_play_event_model(scrobble)
        return _to_legacy_play_event(model_event)
    except Exception:  # pragma: no cover
        log.exception("Error parsing play event")
        raise


def _resolve_played_at(payload: TrackPayload, played_at: datetime | None) -> datetime:
    if played_at is not None:
        return played_at
    if payload.is_now_playing:
        return datetime.now(UTC)
    if payload.date is not None:
        return datetime.fromtimestamp(payload.date.uts, tz=UTC)
    raise ValueError("Invalid scrobble")


def parse_play_event_model(
    scrobble: TrackPayloadInput,
    *,
    played_at: datetime | None = None,
    user: User | None = None,
) -> ModelPlayEvent:
    """Return a domain.model PlayEvent.

    The caller may pass a shared `user` instance to keep ownership stable across a batch.
    """

    payload = _ensure_track_payload(scrobble)
    when = _resolve_played_at(payload, played_at)

    if not payload.album.title:
        log.warning(
            "No album title given for Recording %s by Artist %s", payload.name, payload.artist.name
        )

    active_user = user or User(display_name="Last.fm")
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
    if payload.album.mbid:
        release_set.add_external_id(ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP, payload.album.mbid)

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


def _to_legacy_play_event(model_event: ModelPlayEvent) -> LegacyPlayEvent:
    builder = _LegacyGraphBuilder()
    recording, track, provider = builder.build_from_event(model_event)

    legacy_event = LegacyPlayEvent(
        played_at=model_event.played_at,
        source=provider,
        recording=recording,
        track=track,
    )
    recording.play_events.append(legacy_event)
    track.play_events.append(legacy_event)
    return legacy_event


class _LegacyGraphBuilder:
    def __init__(self) -> None:
        self._artists_by_resolved_id: dict[str, LegacyArtist] = {}

    def build_from_event(
        self, model_event: ModelPlayEvent
    ) -> tuple[LegacyRecording, LegacyTrack, LegacyProvider]:
        provider = LegacyProvider(model_event.source.value)
        model_track = model_event.track
        if model_track is None:
            raise ValueError("Last.fm translation requires track-based PlayEvent")

        legacy_release_set = self._release_set(model_track.release.release_set)
        legacy_release = self._release(model_track.release, legacy_release_set)
        legacy_recording = self._recording(model_event.recording)
        legacy_track = self._track(model_track, legacy_release, legacy_recording)

        legacy_release_set.releases.append(legacy_release)
        legacy_release.tracks.append(legacy_track)
        legacy_recording.tracks.append(legacy_track)

        self._wire_release_set_artists(model_track.release.release_set, legacy_release_set)
        self._wire_recording_artists(model_event.recording, legacy_recording)

        return legacy_recording, legacy_track, provider

    def _artist(self, model_artist: Artist) -> LegacyArtist:
        key = str(model_artist.resolved_id)
        existing = self._artists_by_resolved_id.get(key)
        if existing is not None:
            return existing

        legacy_artist = LegacyArtist(name=model_artist.name)
        self._copy_external_ids(model_artist, legacy_artist)
        self._copy_sources(model_artist, legacy_artist)
        self._artists_by_resolved_id[key] = legacy_artist
        return legacy_artist

    def _release_set(self, model_release_set: ReleaseSet) -> LegacyReleaseSet:
        legacy = LegacyReleaseSet(title=model_release_set.title)
        self._copy_external_ids(model_release_set, legacy)
        self._copy_sources(model_release_set, legacy)
        return legacy

    def _release(self, model_release: Release, release_set: LegacyReleaseSet) -> LegacyRelease:
        legacy = LegacyRelease(title=model_release.title, release_set=release_set)
        self._copy_external_ids(model_release, legacy)
        self._copy_sources(model_release, legacy)
        return legacy

    def _recording(self, model_recording: Recording) -> LegacyRecording:
        legacy = LegacyRecording(title=model_recording.title)
        self._copy_external_ids(model_recording, legacy)
        self._copy_sources(model_recording, legacy)
        return legacy

    def _track(
        self,
        model_track: ReleaseTrack,
        release: LegacyRelease,
        recording: LegacyRecording,
    ) -> LegacyTrack:
        legacy = LegacyTrack(
            release=release,
            recording=recording,
            track_number=model_track.track_number,
            disc_number=model_track.disc_number,
            duration_ms=model_track.duration_ms,
            title_override=model_track.title_override,
        )
        self._copy_sources(model_track, legacy)
        return legacy

    def _wire_release_set_artists(
        self, model_release_set: ReleaseSet, legacy: LegacyReleaseSet
    ) -> None:
        for c in model_release_set.contributions:
            artist = self._artist(c.artist)
            role = LegacyArtistRole(c.role.value) if c.role is not None else None
            link = LegacyReleaseSetArtist(release_set=legacy, artist=artist, role=role)
            legacy.artist_links.append(link)
            artist.release_set_links.append(link)

    def _wire_recording_artists(self, model_recording: Recording, legacy: LegacyRecording) -> None:
        for c in model_recording.contributions:
            artist = self._artist(c.artist)
            role = LegacyArtistRole(c.role.value) if c.role is not None else None
            link = LegacyRecordingArtist(recording=legacy, artist=artist, role=role)
            legacy.artist_links.append(link)
            artist.recording_links.append(link)

    @staticmethod
    def _copy_external_ids(model: _ModelMetadata, legacy: _LegacyExternallyIdentifiable) -> None:
        for ext in model.external_ids:
            provider = LegacyProvider(ext.provider.value) if ext.provider is not None else None
            legacy.add_external_id(str(ext.namespace), ext.value, provider=provider)

    @staticmethod
    def _copy_sources(model: Provenanced, legacy: _LegacySourced) -> None:
        if model.provenance is None:
            return
        for source in model.provenance.sources:
            legacy.sources.add(LegacyProvider(source.value))
