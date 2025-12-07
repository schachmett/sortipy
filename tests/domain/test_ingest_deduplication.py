from __future__ import annotations

from sortipy.domain.ingest_pipeline import (
    DefaultDeduplicationPhase,
    DefaultNormalizationPhase,
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
    release_set.artists.extend(
        [
            ReleaseSetArtist(
                release_set=release_set, artist=artist_primary, role=ArtistRole.PRIMARY
            ),
            ReleaseSetArtist(
                release_set=release_set, artist=artist_duplicate, role=ArtistRole.PRIMARY
            ),
        ]
    )
    artist_primary.release_sets.append(release_set)
    artist_duplicate.release_sets.append(release_set)

    recording.tracks.append(track)
    recording.artists.extend(
        [
            RecordingArtist(recording=recording, artist=artist_primary, role=ArtistRole.PRIMARY),
            RecordingArtist(recording=recording, artist=artist_duplicate, role=ArtistRole.PRIMARY),
        ]
    )
    artist_primary.recordings.append(recording)
    artist_duplicate.recordings.append(recording)
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
    DefaultNormalizationPhase().run(graph, context=context)
    DefaultDeduplicationPhase().run(graph, context=context)

    assert len(graph.artists) == 1
    surviving_artist = graph.artists[0]
    assert surviving_artist is artist_primary
    assert surviving_artist.country == "GB"
    assert any(
        ext.namespace == ExternalNamespace.MUSICBRAINZ_ARTIST and ext.value == "mbid-1234"
        for ext in surviving_artist.external_ids
    )

    assert all(link.artist is surviving_artist for link in release_set.artists)
    assert all(link.artist is surviving_artist for link in recording.artists)

    assert context.dedup_collapsed == 1
