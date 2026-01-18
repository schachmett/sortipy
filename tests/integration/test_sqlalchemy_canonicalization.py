from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from sortipy.domain.ingest_pipeline import run_ingest_pipeline
from sortipy.domain.ingest_pipeline.context import NormalizationState
from sortipy.domain.ingest_pipeline.entity_ops import normalize_artist
from sortipy.domain.ingest_pipeline.orchestrator import IngestGraph
from sortipy.domain.model import Artist, ExternalNamespace

if TYPE_CHECKING:
    from collections.abc import Callable

    from sortipy.adapters.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork


def test_canonicalization_matches_existing_external_id(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    existing = Artist(name="Radiohead")
    existing.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, "mbid-1")

    with sqlite_unit_of_work() as uow:
        uow.repositories.artists.add(existing)
        uow.commit()

    ingest_artist = Artist(name="radiohead")
    ingest_artist.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, "mbid-1")
    graph = IngestGraph(artists=[ingest_artist])

    with sqlite_unit_of_work() as uow:
        run_ingest_pipeline(graph=graph, uow=uow)

    assert graph.artists[0].id == existing.id

    with sqlite_unit_of_work() as uow:
        persisted = uow.session.execute(select(Artist)).scalars().all()
        assert len(persisted) == 1


def test_canonicalization_matches_sidecar_keys(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    existing = Artist(name="Kendrick Lamar")
    state = NormalizationState()
    data = normalize_artist(existing, state)

    with sqlite_unit_of_work() as uow:
        uow.repositories.artists.add(existing)
        uow.repositories.normalization_sidecars.save(existing, data)
        uow.commit()

    ingest_artist = Artist(name="kendrick lamar")
    graph = IngestGraph(artists=[ingest_artist])

    with sqlite_unit_of_work() as uow:
        run_ingest_pipeline(graph=graph, uow=uow)

    assert graph.artists[0].id == existing.id
