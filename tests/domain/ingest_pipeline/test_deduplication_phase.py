from __future__ import annotations

import pytest

from sortipy.domain.ingest_pipeline.context import IngestGraph, PipelineContext
from sortipy.domain.ingest_pipeline.deduplication import DeduplicationPhase
from sortipy.domain.ingest_pipeline.normalization import NormalizationPhase
from sortipy.domain.model import (
    Artist,
    ArtistRole,
    ExternalNamespace,
    Recording,
    ReleaseSet,
)


def test_artist_dedup_prefers_musicbrainz_id_and_merges_metadata() -> None:
    artist_primary = Artist(name="Radiohead")
    artist_duplicate = Artist(name="radiohead", country="GB")
    artist_duplicate.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, "mbid-1234")

    release_set = ReleaseSet(title="Kid A")
    release = release_set.create_release(title="Kid A")
    recording = Recording(title="Everything In Its Right Place")
    release.add_track(recording)

    release_set.add_artist(artist_primary, role=ArtistRole.PRIMARY)
    release_set.add_artist(artist_duplicate, role=ArtistRole.PRIMARY)

    recording.add_artist(artist_primary, role=ArtistRole.PRIMARY)
    recording.add_artist(artist_duplicate, role=ArtistRole.PRIMARY)

    graph = IngestGraph(
        artists=[artist_primary, artist_duplicate],
        release_sets=[release_set],
        releases=[release],
        recordings=[recording],
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

    assert all(c.artist is surviving_artist for c in release_set.contributions)
    assert all(c.artist is surviving_artist for c in recording.contributions)

    entity_type = surviving_artist.entity_type
    assert context.counters.dedup_collapsed == {entity_type: 1}


def test_deduplication_requires_normalization_state() -> None:
    graph = IngestGraph(artists=[Artist(name="No Normalize")])
    context = PipelineContext()

    with pytest.raises(RuntimeError, match="Normalization must run before deduplication"):
        DeduplicationPhase().run(graph, context=context)
