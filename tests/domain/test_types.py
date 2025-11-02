from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sortipy.domain.types import (
    Artist,
    ArtistRole,
    CanonicalEntityType,
    ExternalNamespace,
    Label,
    PartialDate,
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
    artist.sources.add(Provider.LASTFM)
    artist.sources.add(Provider.SPOTIFY)

    assert artist.sources == {Provider.LASTFM, Provider.SPOTIFY}


def test_external_ids_replace_by_namespace() -> None:
    artist = Artist(name="External ID Test")
    artist.add_external_id(ExternalNamespace.SPOTIFY_ARTIST, "artist-1")
    assert len(artist.external_ids) == 1
    assert artist.external_ids[0].value == "artist-1"
    assert artist.external_ids[0].provider is Provider.SPOTIFY

    artist.add_external_id(ExternalNamespace.SPOTIFY_ARTIST, "artist-2", replace=True)
    assert len(artist.external_ids) == 1
    assert artist.external_ids[0].value == "artist-2"


def test_external_ids_by_namespace_property() -> None:
    artist = Artist(name="Mapping Test")
    artist.add_external_id(ExternalNamespace.SPOTIFY_ARTIST, "artist-spotify")
    artist.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, "artist-mbid")

    mapping = artist.external_ids_by_namespace
    assert mapping[ExternalNamespace.SPOTIFY_ARTIST].value == "artist-spotify"
    assert mapping[ExternalNamespace.MUSICBRAINZ_ARTIST].value == "artist-mbid"


def test_add_external_id_allows_custom_provider() -> None:
    artist = Artist(name="Custom Provider")
    artist.add_external_id(
        namespace="custom:catalogue",
        value="identifier",
        provider=Provider.LASTFM,
    )

    external_id = artist.external_ids[0]
    assert external_id.namespace == "custom:catalogue"
    assert external_id.provider is Provider.LASTFM


def test_partial_date_helpers() -> None:
    exact = PartialDate(year=2024, month=5, day=10)
    assert exact.as_date == date(2024, 5, 10)

    partial_month = PartialDate(year=1999, month=None, day=None)
    assert partial_month.as_date == date(1999, 1, 1)

    undefined = PartialDate()
    assert undefined.as_date is None

    composite = PartialDate(year=2001, month=12, day=None)
    assert composite.__composite_values__() == (2001, 12, None)


def test_entity_type_properties() -> None:
    artist = Artist(name="Type Test Artist")
    release_set = ReleaseSet(title="Type Test Release Set")
    release = Release(title="Type Test Release", release_set=release_set)
    recording = Recording(title="Type Test Recording")
    track = Track(release=release, recording=recording)
    label = Label(name="Type Test Label")

    assert artist.entity_type is CanonicalEntityType.ARTIST
    assert release_set.entity_type is CanonicalEntityType.RELEASE_SET
    assert release.entity_type is CanonicalEntityType.RELEASE
    assert recording.entity_type is CanonicalEntityType.RECORDING
    assert track.entity_type is CanonicalEntityType.TRACK
    assert label.entity_type is CanonicalEntityType.LABEL
