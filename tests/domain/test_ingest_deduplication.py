from __future__ import annotations

from sortipy.domain.ingest_pipeline import (
    DeduplicationPhase,
    NormalizationPhase,
)
from sortipy.domain.ingest_pipeline.orchestrator import IngestGraph, PipelineContext
from sortipy.domain.types import (
    Artist,
    ArtistRole,
    ExternalNamespace,
    Recording,
    RecordingArtist,
    Release,
    ReleaseSet,
    ReleaseSetArtist,
    Track,
)


def test_artist_dedup_prefers_musicbrainz_id_and_merges_metadata() -> None:
    artist_primary = Artist(name="Radiohead")
    artist_duplicate = Artist(name="radiohead", country="GB")
    artist_duplicate.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, "mbid-1234")

    release_set = ReleaseSet(title="Kid A")
    release = Release(title="Kid A", release_set=release_set)
    recording = Recording(title="Everything In Its Right Place")
    track = Track(release=release, recording=recording)

    release_set.releases.append(release)
    release_set_artist_primary = ReleaseSetArtist(
        release_set=release_set, artist=artist_primary, role=ArtistRole.PRIMARY
    )
    release_set_artist_duplicate = ReleaseSetArtist(
        release_set=release_set, artist=artist_duplicate, role=ArtistRole.PRIMARY
    )
    release_set.artist_links.extend([release_set_artist_primary, release_set_artist_duplicate])
    artist_primary.release_set_links.append(release_set_artist_primary)
    artist_duplicate.release_set_links.append(release_set_artist_duplicate)

    recording.tracks.append(track)
    recording_artist_primary = RecordingArtist(
        recording=recording, artist=artist_primary, role=ArtistRole.PRIMARY
    )
    recording_artist_duplicate = RecordingArtist(
        recording=recording, artist=artist_duplicate, role=ArtistRole.PRIMARY
    )
    recording.artist_links.extend([recording_artist_primary, recording_artist_duplicate])
    artist_primary.recording_links.append(recording_artist_primary)
    artist_duplicate.recording_links.append(recording_artist_duplicate)
    release.tracks.append(track)

    graph = IngestGraph(
        artists=[artist_primary, artist_duplicate],
        release_sets=[release_set],
        releases=[release],
        recordings=[recording],
        tracks=[track],
        play_events=[],
    )

    context = PipelineContext()
    NormalizationPhase().run(graph, context=context)
    DeduplicationPhase().run(graph, context=context)

    assert len(graph.artists) == 1
    surviving_artist = graph.artists[0]
    assert surviving_artist is artist_primary
    assert surviving_artist.country == "GB"
    assert any(
        ext.namespace == ExternalNamespace.MUSICBRAINZ_ARTIST and ext.value == "mbid-1234"
        for ext in surviving_artist.external_ids
    )

    assert all(link.artist is surviving_artist for link in release_set.artist_links)
    assert all(link.artist is surviving_artist for link in recording.artist_links)

    assert context.dedup_collapsed == 1
