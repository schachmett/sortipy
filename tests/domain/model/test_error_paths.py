from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sortipy.domain.model import Artist, PlayEvent, Provider, Recording, ReleaseSet, User


def test_play_event_requires_track_or_recording_ref() -> None:
    user = User(display_name="Listener")
    played_at = datetime(2024, 1, 1, tzinfo=UTC)
    recording = Recording(title="Track")
    release_set = ReleaseSet(title="Album")
    release = release_set.create_release(title="Album")
    track = release.add_track(recording)

    with pytest.raises(ValueError, match="exactly one of track or recording_ref"):
        PlayEvent(
            played_at=played_at,
            source=Provider.LASTFM,
            _user=user,
            _track=None,
            _recording_ref=None,
        )

    with pytest.raises(ValueError, match="exactly one of track or recording_ref"):
        PlayEvent(
            played_at=played_at,
            source=Provider.LASTFM,
            _user=user,
            _track=track,
            _recording_ref=recording,
        )


def test_release_set_remove_release_requires_ownership() -> None:
    a = ReleaseSet(title="A")
    b = ReleaseSet(title="B")
    release = b.create_release(title="Other")

    with pytest.raises(ValueError, match="release not owned"):
        a.remove_release(release)


def test_release_move_track_to_recording_requires_owner() -> None:
    release_set = ReleaseSet(title="Album")
    release = release_set.create_release(title="Album")
    other_release = release_set.create_release(title="Other")
    recording = Recording(title="Track")
    track = release.add_track(recording, track_number=1)

    with pytest.raises(ValueError, match="track not owned"):
        other_release.move_track_to_recording(track, Recording(title="New"))


def test_release_set_remove_artist_requires_link() -> None:
    release_set = ReleaseSet(title="Album")
    artist = Artist(name="Radiohead")

    with pytest.raises(ValueError, match="artist not linked"):
        release_set.remove_artist(artist)


def test_recording_remove_artist_requires_link() -> None:
    recording = Recording(title="Track")
    artist = Artist(name="Radiohead")

    with pytest.raises(ValueError, match="artist not linked"):
        recording.remove_artist(artist)


def test_user_move_play_event_to_rejects_tracked_events() -> None:
    user = User(display_name="Listener")
    recording = Recording(title="Track")
    release_set = ReleaseSet(title="Album")
    release = release_set.create_release(title="Album")
    track = release.add_track(recording)

    event = user.log_play(
        played_at=datetime(2024, 1, 1, tzinfo=UTC),
        source=Provider.LASTFM,
        recording=recording,
        track=track,
    )

    with pytest.raises(ValueError, match="already linked to a track"):
        user.move_play_event_to(event, Recording(title="Other"))
