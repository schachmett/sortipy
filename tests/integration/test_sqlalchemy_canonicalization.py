from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from sortipy.application.claim_graphs import build_catalog_claim_graph
from sortipy.domain.model import (
    Artist,
    ArtistRole,
    ExternalNamespace,
    Provider,
    Recording,
    Release,
    ReleaseSet,
)
from sortipy.domain.reconciliation import ReconciliationEngine, ResolvedResolution

if TYPE_CHECKING:
    from collections.abc import Callable

    from sortipy.adapters.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork


def test_reconciliation_matches_existing_external_id(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    existing = Artist(name="Radiohead")
    existing.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, "mbid-1")

    with sqlite_unit_of_work() as uow:
        uow.repositories.artists.add(existing)
        uow.commit()

    incoming = Artist(name="radiohead")
    incoming.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, "mbid-1")
    graph_result = build_catalog_claim_graph(roots=(incoming,), source=Provider.LASTFM)
    engine = ReconciliationEngine.default()

    with sqlite_unit_of_work() as uow:
        prepared = engine.prepare(graph_result.graph, repositories=uow.repositories)
        resolution = prepared.entity_resolutions_by_claim[
            graph_result.representative_entity_claim_id(
                incoming,
                representatives_by_claim=prepared.representatives_by_claim,
            )
        ]
        assert isinstance(resolution, ResolvedResolution)
        assert resolution.target.id == existing.id


def test_reconciliation_does_not_flush_merged_release_duplicate_subtree(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    existing_artist = Artist(name="Existing Artist")
    existing_artist.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, "artist-1")
    existing_release_set = ReleaseSet(title="Existing Set")
    existing_release_set.add_artist(existing_artist, role=ArtistRole.PRIMARY)
    existing_release = existing_release_set.create_release(title="Existing Release")
    existing_release.add_external_id(ExternalNamespace.MUSICBRAINZ_RELEASE, "release-1")
    existing_recording = Recording(title="Existing Track")
    existing_recording.add_external_id(ExternalNamespace.MUSICBRAINZ_RECORDING, "recording-1")
    existing_recording.add_artist(existing_artist, role=ArtistRole.PRIMARY)
    existing_release.add_track(existing_recording)

    with sqlite_unit_of_work() as uow:
        uow.repositories.artists.add(existing_artist)
        uow.repositories.recordings.add(existing_recording)
        uow.repositories.release_sets.add(existing_release_set)
        uow.commit()

    incoming_artist = Artist(name="Incoming Artist")
    incoming_artist.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, "artist-1")
    incoming_release_set = ReleaseSet(title="Incoming Set")
    incoming_release_set.add_artist(incoming_artist, role=ArtistRole.PRIMARY)
    incoming_release = incoming_release_set.create_release(title="Incoming Release")
    incoming_release.add_external_id(ExternalNamespace.MUSICBRAINZ_RELEASE, "release-1")
    incoming_recording = Recording(title="Incoming Track")
    incoming_recording.add_external_id(ExternalNamespace.MUSICBRAINZ_RECORDING, "recording-1")
    incoming_recording.add_artist(incoming_artist, role=ArtistRole.PRIMARY)
    incoming_release.add_track(incoming_recording)

    graph_result = build_catalog_claim_graph(roots=(incoming_recording,), source=Provider.LASTFM)
    engine = ReconciliationEngine.default()

    with sqlite_unit_of_work() as uow:
        executed = engine.reconcile(graph_result.graph, uow=uow)
        assert executed.persistence_result.persisted_entities == 1

    with sqlite_unit_of_work() as uow:
        artists = uow.session.execute(select(Artist)).scalars().all()
        recordings = uow.session.execute(select(Recording)).scalars().all()
        releases = uow.session.execute(select(Release)).scalars().all()
        release_sets = uow.session.execute(select(ReleaseSet)).scalars().all()
        incoming_release_set_row = next(
            release_set for release_set in release_sets if release_set.title == "Incoming Set"
        )

        assert len(artists) == 1
        assert len(recordings) == 1
        assert len(releases) == 1
        assert len(incoming_release_set_row.releases) == 1


def test_reconciliation_matches_sidecar_keys(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    existing = Artist(name="Kendrick Lamar")
    engine = ReconciliationEngine.default()
    seed_graph = build_catalog_claim_graph(roots=(existing,), source=Provider.LASTFM)

    with sqlite_unit_of_work() as uow:
        executed = engine.reconcile(seed_graph.graph, uow=uow)
        assert executed.persistence_result.persisted_entities == 1

    incoming = Artist(name="kendrick lamar")
    graph_result = build_catalog_claim_graph(roots=(incoming,), source=Provider.SPOTIFY)

    with sqlite_unit_of_work() as uow:
        prepared = engine.prepare(graph_result.graph, repositories=uow.repositories)
        resolution = prepared.entity_resolutions_by_claim[
            graph_result.representative_entity_claim_id(
                incoming,
                representatives_by_claim=prepared.representatives_by_claim,
            )
        ]
        assert isinstance(resolution, ResolvedResolution)
        assert resolution.target.id == existing.id
