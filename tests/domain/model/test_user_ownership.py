from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sortipy.domain.model import Artist, Provider, Recording, Release, ReleaseSet, User


def test_user_save_entity_creates_library_item() -> None:
    user = User(display_name="Default")
    artist = Artist(name="Radiohead")

    item = user.save_entity(artist, source=Provider.LASTFM)

    assert item.user is user
    assert item.target_id == artist.resolved_id
    assert item.target is artist
    assert item.source is Provider.LASTFM
    assert item in user.library_items


def test_user_remove_library_item_requires_ownership() -> None:
    user_a = User(display_name="A")
    user_b = User(display_name="B")
    artist = Artist(name="Radiohead")
    item = user_a.save_entity(artist)

    with pytest.raises(ValueError, match="not owned"):
        user_b.remove_library_item(item)


def test_user_log_play_attaches_event_to_user_and_recording() -> None:
    user = User(display_name="Default")
    recording = Recording(title="Airbag")
    played_at = datetime(2024, 1, 1, tzinfo=UTC)

    event = user.log_play(played_at=played_at, source=Provider.LASTFM, recording=recording)

    assert event in user.play_events
    assert event.user is user
    assert event.recording is recording


def test_user_log_play_with_track_sets_track_and_derived_recording() -> None:
    user = User(display_name="Default")
    release_set = ReleaseSet(title="OK Computer")
    release = Release(title="OK Computer", _release_set=release_set)
    recording = Recording(title="Airbag")
    track = release.add_track(recording, track_number=1)

    event = user.log_play(
        played_at=datetime(2024, 1, 1, tzinfo=UTC),
        source=Provider.LASTFM,
        recording=recording,
        track=track,
    )

    assert event.track is track
    assert event.recording is recording
    assert event.release is release


def test_user_log_play_rejects_mismatched_track_and_recording() -> None:
    user = User(display_name="Default")
    release_set = ReleaseSet(title="OK Computer")
    release = Release(title="OK Computer", _release_set=release_set)
    recording_a = Recording(title="Airbag")
    recording_b = Recording(title="Paranoid Android")
    track = release.add_track(recording_a, track_number=1)

    with pytest.raises(ValueError, match="track\\.recording must match recording"):
        user.log_play(
            played_at=datetime(2024, 1, 1, tzinfo=UTC),
            source=Provider.LASTFM,
            recording=recording_b,
            track=track,
        )


def test_user_link_play_to_track_moves_from_recording_ref_to_track() -> None:
    user = User(display_name="Default")
    release_set = ReleaseSet(title="OK Computer")
    release = Release(title="OK Computer", _release_set=release_set)
    recording = Recording(title="Airbag")
    track = release.add_track(recording, track_number=1)

    event = user.log_play(
        played_at=datetime(2024, 1, 1, tzinfo=UTC),
        source=Provider.LASTFM,
        recording=recording,
        track=None,
    )
    assert event.track is None
    assert event.recording_ref is recording

    user.link_play_to_track(event, track)
    assert event.track is track
    assert event.recording_ref is None


def test_user_link_play_to_track_rejects_wrong_recording() -> None:
    user = User(display_name="Default")
    release_set = ReleaseSet(title="OK Computer")
    release = Release(title="OK Computer", _release_set=release_set)
    recording_a = Recording(title="Airbag")
    recording_b = Recording(title="Paranoid Android")
    track = release.add_track(recording_a, track_number=1)

    event = user.log_play(
        played_at=datetime(2024, 1, 1, tzinfo=UTC),
        source=Provider.LASTFM,
        recording=recording_b,
        track=None,
    )

    with pytest.raises(ValueError, match="track\\.recording must match play event recording"):
        user.link_play_to_track(event, track)
