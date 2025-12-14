from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select

from sortipy.adapters.sqlalchemy.mappings import canonical_source_table
from sortipy.adapters.sqlalchemy.sidecar_mappings import normalization_sidecar_table
from sortipy.adapters.sqlalchemy.unit_of_work import (
    SqlAlchemyIngestUnitOfWork,
    shutdown,
    startup,
)
from sortipy.domain.ingest_pipeline import (
    CanonicalizationPhase,
    DeduplicationPhase,
    IngestGraph,
    IngestionPipeline,
    NormalizationPhase,
    PipelineContext,
)
from sortipy.domain.ingest_pipeline.entity_ops import normalize_artist
from sortipy.domain.types import Artist, ExternalNamespace

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.engine import Engine


@pytest.fixture
def ingest_db(sqlite_engine: Engine) -> Iterator[Engine]:
    startup(engine=sqlite_engine, force=True)
    normalization_sidecar_table.create(sqlite_engine, checkfirst=True)
    canonical_source_table.create(sqlite_engine, checkfirst=True)
    try:
        yield sqlite_engine
    finally:
        shutdown()


def _pipeline() -> IngestionPipeline:
    return IngestionPipeline(
        phases=(
            NormalizationPhase(),
            DeduplicationPhase(),
            CanonicalizationPhase(),
        )
    )


@pytest.mark.usefixtures("ingest_db")
def test_canonicalization_matches_external_id() -> None:
    existing = Artist(name="Radiohead")
    existing.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, "mbid-1")

    with SqlAlchemyIngestUnitOfWork() as uow:
        uow.repositories.artists.add(existing)
        uow.commit()

    ingest_artist = Artist(name="radiohead")
    ingest_artist.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, "mbid-1")

    graph = IngestGraph(artists=[ingest_artist])

    with SqlAlchemyIngestUnitOfWork() as uow:
        context = PipelineContext(ingest_uow=uow)
        _pipeline().run(graph, context=context)

    assert graph.artists[0].id == existing.id

    with uow:
        count = uow.session.execute(select(func.count()).select_from(Artist)).scalar_one()
        assert count == 1


@pytest.mark.usefixtures("ingest_db")
def test_canonicalization_matches_deterministic_keys() -> None:
    existing = Artist(name="Kendrick Lamar")
    sidecar_data = normalize_artist(existing)

    with SqlAlchemyIngestUnitOfWork() as uow:
        repos = uow.repositories
        repos.artists.add(existing)
        repos.normalization_sidecars.save(existing, sidecar_data)
        uow.commit()

    ingest_artist = Artist(name="kendrick lamar")
    graph = IngestGraph(artists=[ingest_artist])
    with uow:
        context = PipelineContext(ingest_uow=uow)
        _pipeline().run(graph, context=context)

    assert graph.artists[0].id == existing.id
