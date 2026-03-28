from __future__ import annotations

from sortipy.domain.model import Artist, ArtistRole, Recording, Release, ReleaseSet


def test_release_set_add_release_maintains_release_set_pointer() -> None:
    a = ReleaseSet(title="A")
    b = ReleaseSet(title="B")
    release = Release(title="Example", _release_set=b)

    a.add_release(release)

    assert release.release_set is a
    assert release in a.releases


def test_release_set_create_release_attaches_and_returns_release() -> None:
    release_set = ReleaseSet(title="OK Computer")

    release = release_set.create_release(title="OK Computer", format_="CD", medium_count=1)

    assert release.release_set is release_set
    assert release in release_set.releases
    assert release.title == "OK Computer"
    assert release.format == "CD"
    assert release.medium_count == 1


def test_release_set_add_artist_creates_bidirectional_contribution() -> None:
    artist = Artist(name="Radiohead")
    release_set = ReleaseSet(title="OK Computer")
    c = release_set.add_artist(artist, role=ArtistRole.PRIMARY)

    assert c in release_set.contributions
    assert c.release_set is release_set
    assert c.artist is artist

    assert c in artist.release_set_contributions
    assert release_set in artist.release_sets


def test_recording_add_artist_creates_bidirectional_contribution() -> None:
    artist = Artist(name="Radiohead")
    recording = Recording(title="Paranoid Android")
    c = recording.add_artist(artist)

    assert c in recording.contributions
    assert c.recording is recording
    assert c.artist is artist

    assert c in artist.recording_contributions
    assert recording in artist.recordings


def test_release_add_track_attaches_release_track_to_recording() -> None:
    release_set = ReleaseSet(title="OK Computer")
    release = Release(title="OK Computer", _release_set=release_set)
    recording = Recording(title="Airbag")

    track = release.add_track(recording, track_number=1)

    assert track in release.tracks
    assert track.release is release
    assert track.recording is recording
    assert track in recording.release_tracks
    assert release in recording.releases


def test_release_set_adopt_contribution_rehomes_existing_association() -> None:
    original_release_set = ReleaseSet(title="Original")
    target_release_set = ReleaseSet(title="Target")
    original_artist = Artist(name="Original Artist")
    target_artist = Artist(name="Target Artist")
    contribution = original_release_set.add_artist(original_artist, role=ArtistRole.PRIMARY)

    adopted = target_release_set.adopt_contribution(contribution, artist=target_artist)

    assert adopted is contribution
    assert contribution.release_set is target_release_set
    assert contribution.artist is target_artist
    assert contribution not in original_release_set.contributions
    assert contribution in target_release_set.contributions
    assert contribution not in original_artist.release_set_contributions
    assert contribution in target_artist.release_set_contributions


def test_recording_adopt_contribution_rehomes_existing_association() -> None:
    original_recording = Recording(title="Original")
    target_recording = Recording(title="Target")
    original_artist = Artist(name="Original Artist")
    target_artist = Artist(name="Target Artist")
    contribution = original_recording.add_artist(original_artist)

    adopted = target_recording.adopt_contribution(contribution, artist=target_artist)

    assert adopted is contribution
    assert contribution.recording is target_recording
    assert contribution.artist is target_artist
    assert contribution not in original_recording.contributions
    assert contribution in target_recording.contributions
    assert contribution not in original_artist.recording_contributions
    assert contribution in target_artist.recording_contributions


def test_release_adopt_track_rehomes_existing_association() -> None:
    original_release_set = ReleaseSet(title="Original")
    target_release_set = ReleaseSet(title="Target")
    original_release = original_release_set.create_release(title="Original Release")
    target_release = target_release_set.create_release(title="Target Release")
    original_recording = Recording(title="Original Recording")
    target_recording = Recording(title="Target Recording")
    track = original_release.add_track(original_recording, track_number=1)

    adopted = target_release.adopt_track(track, recording=target_recording)

    assert adopted is track
    assert track.release is target_release
    assert track.recording is target_recording
    assert track not in original_release.tracks
    assert track in target_release.tracks
    assert track not in original_recording.release_tracks
    assert track in target_recording.release_tracks
