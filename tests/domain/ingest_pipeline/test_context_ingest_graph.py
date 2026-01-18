from __future__ import annotations

from datetime import UTC, datetime

from sortipy.domain.ingest_pipeline import ingest_graph_from_events
from sortipy.domain.ingest_pipeline.orchestrator import IngestGraph
from sortipy.domain.model import Artist, ArtistRole, Provider, Recording, ReleaseSet, User


def test_model_ingest_graph_collects_roots_without_tracks() -> None:
    user = User(display_name="Last.fm")
    artist = Artist(name="Boards of Canada")
    release_set = ReleaseSet(title="Music Has the Right to Children")
    release = release_set.create_release(title="Music Has the Right to Children")
    recording = Recording(title="Roygbiv")
    track = release.add_track(recording)

    release_set.add_artist(artist, role=ArtistRole.PRIMARY)
    recording.add_artist(artist, role=ArtistRole.PRIMARY)

    event = user.log_play(
        played_at=datetime(2024, 1, 1, tzinfo=UTC),
        source=Provider.LASTFM,
        recording=recording,
        track=track,
    )

    graph = ingest_graph_from_events([event])

    assert isinstance(graph, IngestGraph)
    assert graph.users == [user]
    assert graph.play_events == [event]
    assert graph.recordings == [recording]
    assert graph.artists == [artist]
    assert graph.releases == [release]
    assert graph.release_sets == [release_set]
    assert not hasattr(graph, "tracks")
