from __future__ import annotations

from datetime import UTC, datetime

from sortipy.domain.ingest_pipeline.context import NormalizationState
from sortipy.domain.ingest_pipeline.entity_ops import (
    absorb_play_event,
    absorb_recording,
    absorb_release,
    absorb_release_set,
    normalize_artist,
    normalize_play_event,
    normalize_recording,
    normalize_release,
    normalize_release_set,
)
from sortipy.domain.model import (
    Artist,
    ArtistRole,
    ExternalNamespace,
    Label,
    Provider,
    Recording,
    ReleaseSet,
    User,
)


def _store_artist(state: NormalizationState, artist: Artist) -> None:
    state.store(artist, normalize_artist(artist, state))


def test_normalize_release_set_uses_primary_artist_from_state() -> None:
    primary = Artist(name="Radiohead")
    featured = Artist(name="Guest")
    release_set = ReleaseSet(title="OK Computer")
    release_set.add_artist(primary, role=ArtistRole.PRIMARY)
    release_set.add_artist(featured, role=ArtistRole.FEATURED)

    state = NormalizationState()
    _store_artist(state, primary)
    _store_artist(state, featured)

    data = normalize_release_set(release_set, state)
    primary_data = state.fetch(primary)
    assert primary_data is not None
    assert data.normalized_primary_artist_name == primary_data.normalized_name


def test_normalize_release_prefers_release_set_artist_name() -> None:
    primary = Artist(name="Radiohead")
    release_set = ReleaseSet(title="Kid A")
    release_set.add_artist(primary, role=ArtistRole.PRIMARY)
    release = release_set.create_release(title="Kid A")

    state = NormalizationState()
    _store_artist(state, primary)
    state.store(release_set, normalize_release_set(release_set, state))

    data = normalize_release(release, state)
    release_set_data = state.fetch(release_set)
    assert release_set_data is not None
    assert data.normalized_artist_name == release_set_data.normalized_primary_artist_name


def test_normalize_recording_uses_duration_bucket_and_artist() -> None:
    artist = Artist(name="Radiohead")
    recording = Recording(title="Everything In Its Right Place", duration_ms=4100)
    recording.add_artist(artist, role=ArtistRole.PRIMARY)

    state = NormalizationState()
    _store_artist(state, artist)

    data = normalize_recording(recording, state)
    artist_data = state.fetch(artist)
    assert artist_data is not None
    assert data.normalized_primary_artist_name == artist_data.normalized_name
    assert data.duration_bin == 2


def test_normalize_play_event_tracks_are_optional() -> None:
    user = User(display_name="Listener")
    recording = Recording(title="Track")
    event = user.log_play(
        played_at=datetime(2024, 1, 1, tzinfo=UTC),
        source=Provider.LASTFM,
        recording=recording,
    )

    data = normalize_play_event(event, NormalizationState())
    assert data.track_id is None

    release_set = ReleaseSet(title="Album")
    release = release_set.create_release(title="Album")
    track = release.add_track(recording)
    event_with_track = user.log_play(
        played_at=datetime(2024, 1, 1, 1, tzinfo=UTC),
        source=Provider.LASTFM,
        recording=recording,
        track=track,
    )

    data_with_track = normalize_play_event(event_with_track, NormalizationState())
    assert data_with_track.track_id == track.resolved_id


def test_absorb_release_set_moves_contributions_and_releases() -> None:
    primary = ReleaseSet(title="Primary")
    duplicate = ReleaseSet(title="Duplicate")
    artist = Artist(name="Radiohead")
    duplicate.add_artist(artist, role=ArtistRole.PRIMARY)
    duplicate.add_external_id(ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP, "mbid-dup")
    duplicate.add_source(Provider.MUSICBRAINZ)

    primary_release = primary.create_release(title="Primary Release")
    duplicate_release = duplicate.create_release(title="Duplicate Release")

    absorb_release_set(primary, duplicate)

    assert duplicate_release.release_set is primary
    assert primary_release in primary.releases
    assert duplicate_release in primary.releases
    assert all(c.release_set is primary for c in primary.contributions)
    assert any(
        ext.namespace == ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP
        and ext.value == "mbid-dup"
        for ext in primary.external_ids
    )
    assert primary.provenance is not None
    assert Provider.MUSICBRAINZ in primary.provenance.sources


def test_absorb_release_moves_tracks_labels_and_external_ids() -> None:
    release_set = ReleaseSet(title="Release Set")
    primary = release_set.create_release(title="Primary")
    duplicate = release_set.create_release(title="Duplicate")

    label = Label(name="XL")
    duplicate.add_label(label)
    recording = Recording(title="Track")
    track = duplicate.add_track(recording, track_number=1)
    duplicate.add_external_id(ExternalNamespace.MUSICBRAINZ_RELEASE, "mbid-release")

    absorb_release(primary, duplicate)

    assert track.release is primary
    assert label in primary.labels
    assert duplicate not in release_set.releases
    assert any(
        ext.namespace == ExternalNamespace.MUSICBRAINZ_RELEASE and ext.value == "mbid-release"
        for ext in primary.external_ids
    )


def test_absorb_recording_moves_contributions_and_tracks() -> None:
    primary = Recording(title="Primary")
    duplicate = Recording(title="Duplicate")
    artist = Artist(name="Radiohead")
    duplicate.add_artist(artist, role=ArtistRole.PRIMARY)

    release_set = ReleaseSet(title="Release Set")
    release = release_set.create_release(title="Album")
    track = release.add_track(duplicate, track_number=1)

    absorb_recording(primary, duplicate)

    assert track.recording is primary
    assert all(c.recording is primary for c in primary.contributions)
    assert duplicate.release_tracks == ()


def test_absorb_play_event_merges_track_and_duration() -> None:
    user = User(display_name="Listener")
    recording = Recording(title="Track")
    release_set = ReleaseSet(title="Album")
    release = release_set.create_release(title="Album")
    track = release.add_track(recording)

    primary = user.log_play(
        played_at=datetime(2024, 1, 1, tzinfo=UTC),
        source=Provider.LASTFM,
        recording=recording,
    )
    duplicate = user.log_play(
        played_at=datetime(2024, 1, 1, 1, tzinfo=UTC),
        source=Provider.LASTFM,
        recording=recording,
        track=track,
        duration_ms=123000,
    )

    absorb_play_event(primary, duplicate)

    assert primary.track is track
    assert primary.duration_ms == 123000
