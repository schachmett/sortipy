"""Exercise SQLAlchemy play-event repository helpers against the new domain model."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session  # noqa: TC002

from sortipy.adapters.sqlalchemy import CanonicalEntityMerger
from sortipy.domain.types import (
    Artist,
    ArtistRole,
    CanonicalEntityType,
    ExternalID,
    ExternalNamespace,
    Recording,
    RecordingArtist,
    Release,
    ReleaseSet,
    ReleaseSetArtist,
    Track,
)


@pytest.fixture
def merger(sqlite_session: Session) -> CanonicalEntityMerger:
    sqlite_session.expire_all()
    return CanonicalEntityMerger(sqlite_session)


def test_merge_artist_reuses_existing_by_mbid(
    merger: CanonicalEntityMerger, sqlite_session: Session
) -> None:
    existing = Artist(name="Stored Artist")
    existing.external_ids.append(
        ExternalID(
            namespace=ExternalNamespace.MUSICBRAINZ_ARTIST.value,
            value="mbid-123",
            entity_type=CanonicalEntityType.ARTIST,
        )
    )
    existing.id = uuid.uuid4()
    sqlite_session.add(existing)
    sqlite_session.commit()

    candidate = Artist(name="Incoming Alias")
    candidate.external_ids.append(
        ExternalID(
            namespace=ExternalNamespace.MUSICBRAINZ_ARTIST.value,
            value="mbid-123",
            entity_type=CanonicalEntityType.ARTIST,
        )
    )
    merged = merger.merge_artist(candidate)

    assert merged is existing


def test_merge_release_reuses_components(
    merger: CanonicalEntityMerger, sqlite_session: Session
) -> None:
    artist = Artist(name="Stored Artist")
    artist.external_ids.append(
        ExternalID(
            namespace=ExternalNamespace.MUSICBRAINZ_ARTIST.value,
            value="artist-1",
            entity_type=CanonicalEntityType.ARTIST,
        )
    )
    release_set = ReleaseSet(title="Stored Release Set")
    release_set.external_ids.append(
        ExternalID(
            namespace=ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP.value,
            value="rs-1",
            entity_type=CanonicalEntityType.RELEASE_SET,
        )
    )
    release_set.artists.append(
        ReleaseSetArtist(
            release_set=release_set,
            artist=artist,
            role=ArtistRole.PRIMARY,
        )
    )
    release = Release(title="Stored Release", release_set=release_set)
    release.external_ids.append(
        ExternalID(
            namespace=ExternalNamespace.MUSICBRAINZ_RELEASE.value,
            value="rel-1",
            entity_type=CanonicalEntityType.RELEASE,
        )
    )
    sqlite_session.add_all([artist, release_set, release])
    sqlite_session.commit()

    incoming_artist = Artist(name="Alt Name")
    incoming_artist.external_ids.append(
        ExternalID(
            namespace=ExternalNamespace.MUSICBRAINZ_ARTIST.value,
            value="artist-1",
            entity_type=CanonicalEntityType.ARTIST,
        )
    )
    incoming_release_set = ReleaseSet(title="Alt Title")
    incoming_release_set.external_ids.append(
        ExternalID(
            namespace=ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP.value,
            value="rs-1",
            entity_type=CanonicalEntityType.RELEASE_SET,
        )
    )
    incoming_release_set.artists.append(
        ReleaseSetArtist(
            release_set=incoming_release_set,
            artist=incoming_artist,
            role=ArtistRole.PRIMARY,
        ),
    )
    incoming_release = Release(title="Alt Release", release_set=incoming_release_set)
    incoming_release.external_ids.append(
        ExternalID(
            namespace=ExternalNamespace.MUSICBRAINZ_RELEASE.value,
            value="rel-1",
            entity_type=CanonicalEntityType.RELEASE,
        )
    )

    merged_release = merger.merge_release(incoming_release)

    assert merged_release is release
    assert merged_release.release_set is release_set
    assert any(link.artist is artist for link in release_set.artists)


def test_merge_recording_reuses_by_mbid(
    merger: CanonicalEntityMerger, sqlite_session: Session
) -> None:
    artist = Artist(name="Stored Artist")
    artist.external_ids.append(
        ExternalID(
            namespace=ExternalNamespace.MUSICBRAINZ_ARTIST.value,
            value="artist-2",
            entity_type=CanonicalEntityType.ARTIST,
        )
    )
    recording = Recording(title="Stored Recording")
    recording.external_ids.append(
        ExternalID(
            namespace=ExternalNamespace.MUSICBRAINZ_RECORDING.value,
            value="rec-1",
            entity_type=CanonicalEntityType.RECORDING,
        )
    )
    recording.artists.append(
        RecordingArtist(recording=recording, artist=artist, role=ArtistRole.PRIMARY)
    )
    sqlite_session.add_all([artist, recording])
    sqlite_session.commit()

    incoming_artist = Artist(name="Incoming")
    incoming_artist.external_ids.append(
        ExternalID(
            namespace=ExternalNamespace.MUSICBRAINZ_ARTIST.value,
            value="artist-2",
            entity_type=CanonicalEntityType.ARTIST,
        )
    )
    incoming_recording = Recording(title="Incoming Recording")
    incoming_recording.external_ids.append(
        ExternalID(
            namespace=ExternalNamespace.MUSICBRAINZ_RECORDING.value,
            value="rec-1",
            entity_type=CanonicalEntityType.RECORDING,
        )
    )
    incoming_recording.artists.append(
        RecordingArtist(
            recording=incoming_recording,
            artist=incoming_artist,
            role=ArtistRole.PRIMARY,
        ),
    )

    merged = merger.merge_recording(incoming_recording)

    assert merged is recording
    assert any(link.artist is artist for link in recording.artists)


def test_merge_track_resolves_existing_relationships(
    merger: CanonicalEntityMerger, sqlite_session: Session
) -> None:
    artist = Artist(name="Stored Artist")
    release_set = ReleaseSet(title="Stored Release Set")
    release_set.artists.append(
        ReleaseSetArtist(
            release_set=release_set,
            artist=artist,
            role=ArtistRole.PRIMARY,
        )
    )
    release = Release(title="Stored Release", release_set=release_set)
    release.external_ids.append(
        ExternalID(
            namespace=ExternalNamespace.MUSICBRAINZ_RELEASE.value,
            value="rel-merge",
            entity_type=CanonicalEntityType.RELEASE,
        )
    )
    recording = Recording(title="Stored Recording")
    recording.external_ids.append(
        ExternalID(
            namespace=ExternalNamespace.MUSICBRAINZ_RECORDING.value,
            value="rec-merge",
            entity_type=CanonicalEntityType.RECORDING,
        )
    )
    recording.artists.append(
        RecordingArtist(recording=recording, artist=artist, role=ArtistRole.PRIMARY)
    )
    track = Track(release=release, recording=recording, track_number=1)
    sqlite_session.add_all([artist, release_set, release, recording, track])
    sqlite_session.commit()

    incoming_recording = Recording(title="Ignored")
    incoming_recording.external_ids.append(
        ExternalID(
            namespace=ExternalNamespace.MUSICBRAINZ_RECORDING.value,
            value="rec-merge",
            entity_type=CanonicalEntityType.RECORDING,
        )
    )
    incoming_recording.artists.append(
        RecordingArtist(recording=incoming_recording, artist=artist, role=ArtistRole.PRIMARY)
    )
    incoming_track = Track(release=release, recording=incoming_recording, track_number=1)

    merged_recording = merger.merge_recording(incoming_track.recording)
    incoming_track.recording = merged_recording

    merged_track = merger.merge_track(incoming_track)

    assert merged_track is track
    assert merged_track.recording is recording
    assert merged_track.release is release
