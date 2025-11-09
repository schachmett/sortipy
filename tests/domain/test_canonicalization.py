from __future__ import annotations

from datetime import UTC, datetime

from sortipy.domain.canonicalization import canonicalize_play_event
from sortipy.domain.ports.unit_of_work import PlayEventRepositories
from sortipy.domain.types import (
    Artist,
    ArtistRole,
    CanonicalEntity,
    ExternalNamespace,
    Namespace,
    PlayEvent,
    Provider,
    Recording,
    RecordingArtist,
    Release,
    ReleaseSet,
    ReleaseSetArtist,
    Track,
)


class _DictRepo[TEntity]:
    def __init__(
        self,
        mapping: dict[tuple[Namespace, str], TEntity] | None = None,
    ) -> None:
        self._mapping = mapping or {}
        self.add_calls: list[TEntity] = []

    def add(self, entity: TEntity) -> None:
        self.add_calls.append(entity)

    def get_by_external_id(self, namespace: Namespace, value: str) -> TEntity | None:
        return self._mapping.get((namespace, value))


class _NullPlayEventRepo:
    def add(self, entity: PlayEvent) -> None:  # pragma: no cover - unused helper
        _ = entity

    def exists(self, timestamp: datetime) -> bool:  # pragma: no cover - unused helper
        _ = timestamp
        return False

    def latest_timestamp(self) -> datetime | None:  # pragma: no cover - unused helper
        return None


def _with_external_id[TCanonical: CanonicalEntity](
    entity: TCanonical,
    namespace: ExternalNamespace,
    value: str,
) -> TCanonical:
    entity.add_external_id(namespace, value)
    return entity


def _make_play_event() -> PlayEvent:
    artist = _with_external_id(
        Artist(name="Fresh Artist"), ExternalNamespace.MUSICBRAINZ_ARTIST, "artist-id"
    )
    release_set = _with_external_id(
        ReleaseSet(title="Fresh Release Set"),
        ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP,
        "release-set-id",
    )
    release_set.artists.append(
        ReleaseSetArtist(release_set=release_set, artist=artist, role=ArtistRole.PRIMARY)
    )
    release = _with_external_id(
        Release(title="Fresh Release", release_set=release_set),
        ExternalNamespace.MUSICBRAINZ_RELEASE,
        "release-id",
    )
    recording = _with_external_id(
        Recording(title="Fresh Recording"),
        ExternalNamespace.MUSICBRAINZ_RECORDING,
        "recording-id",
    )
    recording.artists.append(RecordingArtist(recording=recording, artist=artist))
    track = Track(release=release, recording=recording, track_number=1)
    return PlayEvent(
        played_at=datetime.now(tz=UTC),
        source=Provider.LASTFM,
        recording=recording,
        track=track,
    )


def test_canonicalize_play_event_replaces_entities() -> None:
    existing_artist = Artist(name="Existing Artist")
    existing_artist = _with_external_id(
        existing_artist,
        ExternalNamespace.MUSICBRAINZ_ARTIST,
        "artist-id",
    )
    existing_recording = Recording(title="Existing Recording")
    existing_recording = _with_external_id(
        existing_recording,
        ExternalNamespace.MUSICBRAINZ_RECORDING,
        "recording-id",
    )
    existing_recording.artists.append(
        RecordingArtist(recording=existing_recording, artist=existing_artist)
    )
    existing_release_set = ReleaseSet(title="Existing Release Set")
    existing_release_set = _with_external_id(
        existing_release_set,
        ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP,
        "release-set-id",
    )
    existing_release = Release(title="Existing Release", release_set=existing_release_set)
    existing_release = _with_external_id(
        existing_release,
        ExternalNamespace.MUSICBRAINZ_RELEASE,
        "release-id",
    )

    repos = PlayEventRepositories(
        play_events=_NullPlayEventRepo(),
        artists=_DictRepo[Artist](
            {(ExternalNamespace.MUSICBRAINZ_ARTIST, "artist-id"): existing_artist}
        ),
        release_sets=_DictRepo[ReleaseSet](
            {(ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP, "release-set-id"): existing_release_set}
        ),
        releases=_DictRepo[Release](
            {(ExternalNamespace.MUSICBRAINZ_RELEASE, "release-id"): existing_release}
        ),
        recordings=_DictRepo[Recording](
            {(ExternalNamespace.MUSICBRAINZ_RECORDING, "recording-id"): existing_recording}
        ),
        tracks=_DictRepo[Track](),
    )

    event = _make_play_event()
    canonicalize_play_event(event, repos)

    assert event.recording is existing_recording
    assert event.track is not None
    assert event.track.release is existing_release
    assert event.track.release.release_set is existing_release_set
    assert event.recording.artists[0].artist is existing_artist


def test_canonicalize_play_event_leaves_unknown_entities() -> None:
    repos = PlayEventRepositories(
        play_events=_NullPlayEventRepo(),
        artists=_DictRepo[Artist](),
        release_sets=_DictRepo[ReleaseSet](),
        releases=_DictRepo[Release](),
        recordings=_DictRepo[Recording](),
        tracks=_DictRepo[Track](),
    )

    event = _make_play_event()
    canonicalize_play_event(event, repos)

    assert event.recording.title == "Fresh Recording"
    assert event.track is not None
    assert event.track.release.title == "Fresh Release"


def test_canonicalize_track_reuses_existing_track_on_release() -> None:
    existing_artist = _with_external_id(
        Artist(name="Existing Artist"),
        ExternalNamespace.MUSICBRAINZ_ARTIST,
        "artist-id",
    )
    existing_release_set = _with_external_id(
        ReleaseSet(title="Existing Release Set"),
        ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP,
        "release-set-id",
    )
    existing_release_set.artists.append(
        ReleaseSetArtist(
            release_set=existing_release_set,
            artist=existing_artist,
            role=ArtistRole.PRIMARY,
        )
    )
    existing_release = _with_external_id(
        Release(title="Existing Release", release_set=existing_release_set),
        ExternalNamespace.MUSICBRAINZ_RELEASE,
        "release-id",
    )
    existing_recording = _with_external_id(
        Recording(title="Existing Recording"),
        ExternalNamespace.MUSICBRAINZ_RECORDING,
        "recording-id",
    )
    existing_recording.artists.append(
        RecordingArtist(recording=existing_recording, artist=existing_artist)
    )
    existing_track = Track(
        release=existing_release,
        recording=existing_recording,
        track_number=1,
    )
    existing_release.tracks.append(existing_track)

    repos = PlayEventRepositories(
        play_events=_NullPlayEventRepo(),
        artists=_DictRepo[Artist](
            {(ExternalNamespace.MUSICBRAINZ_ARTIST, "artist-id"): existing_artist}
        ),
        release_sets=_DictRepo[ReleaseSet](
            {(ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP, "release-set-id"): existing_release_set}
        ),
        releases=_DictRepo[Release](
            {(ExternalNamespace.MUSICBRAINZ_RELEASE, "release-id"): existing_release}
        ),
        recordings=_DictRepo[Recording](
            {(ExternalNamespace.MUSICBRAINZ_RECORDING, "recording-id"): existing_recording}
        ),
        tracks=_DictRepo[Track](),
    )

    event = _make_play_event()
    assert event.track is not None
    event.track.track_number = 1
    canonicalize_play_event(event, repos)

    assert event.track is existing_track
    assert event.track.recording is existing_recording
    assert event.track.release is existing_release
