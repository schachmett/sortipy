from __future__ import annotations

from sortipy.domain.model.enums import ArtistRole
from sortipy.domain.model.music import Artist, Recording, Release, ReleaseSet


def test_release_set_add_release_maintains_release_set_pointer() -> None:
    a = ReleaseSet(title="A")
    b = ReleaseSet(title="B")
    release = Release(title="Example", _release_set=b)

    a._add_release(release)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

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
