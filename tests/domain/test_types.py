from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sortipy.domain.types import (
    Artist,
    ArtistRole,
    CanonicalEntityType,
    ExternalID,
    PlayEvent,
    Provider,
    Recording,
    RecordingArtist,
    Release,
    ReleaseSet,
    ReleaseSetArtist,
    Track,
)


def _make_release_graph() -> tuple[Artist, ReleaseSet, Release, Recording, Track]:
    artist = Artist(name="Test Artist")
    release_set = ReleaseSet(title="Example Release Set")
    release = Release(title="Example Release", release_set=release_set)
    recording = Recording(title="Example Recording")
    track = Track(release=release, recording=recording, track_number=1)

    release_set.releases.append(release)
    release.tracks.append(track)
    recording.tracks.append(track)
    release_set.artists.append(
        ReleaseSetArtist(
            release_set=release_set,
            artist=artist,
            role=ArtistRole.PRIMARY,
        )
    )
    recording.artists.append(
        RecordingArtist(recording=recording, artist=artist, role=ArtistRole.PRIMARY)
    )

    return artist, release_set, release, recording, track


def test_canonical_identity_prefers_canonical_id() -> None:
    artist = Artist(name="Identity Test")

    assert artist.identity is None

    generated_id = uuid.uuid4()
    artist.id = generated_id
    assert artist.identity == generated_id

    canonical_id = uuid.uuid4()
    artist.canonical_id = canonical_id
    assert artist.identity == canonical_id


def test_release_structure_links_entities() -> None:
    artist, release_set, release, recording, track = _make_release_graph()
    event = PlayEvent(
        played_at=datetime(2024, 1, 1, tzinfo=UTC),
        source=Provider.LASTFM,
        recording=recording,
        track=track,
    )
    recording.play_events.append(event)
    track.play_events.append(event)

    assert track in release.tracks
    assert release in release_set.releases
    assert track in recording.tracks
    assert event in recording.play_events
    assert event in track.play_events
    assert any(link.artist is artist for link in recording.artists)
    assert any(link.artist is artist for link in release_set.artists)


def test_sources_are_tracked() -> None:
    artist = Artist(name="Source Test")
    artist.add_source(Provider.LASTFM)
    artist.add_source(Provider.SPOTIFY)

    assert artist.sources == {Provider.LASTFM, Provider.SPOTIFY}


def test_external_ids_replace_by_namespace() -> None:
    artist = Artist(name="External ID Test")
    first = ExternalID(
        namespace="spotify:artist",
        value="artist-1",
        entity_type=CanonicalEntityType.ARTIST,
    )
    second = ExternalID(
        namespace="spotify:artist",
        value="artist-2",
        entity_type=CanonicalEntityType.ARTIST,
    )

    artist.add_external_id(first)
    assert artist.external_ids == [first]

    artist.add_external_id(second, replace=True)
    assert artist.external_ids == [second]
