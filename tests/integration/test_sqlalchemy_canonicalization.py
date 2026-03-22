from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from sortipy.domain.model import Artist, ExternalNamespace, Provider
from sortipy.domain.reconciliation import (
    ResolvedResolution,
    build_catalog_claim_graph,
    create_default_reconciliation_engine,
)

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
    bundle = build_catalog_claim_graph(roots=(incoming,), source=Provider.LASTFM)
    engine = create_default_reconciliation_engine()

    with sqlite_unit_of_work() as uow:
        keys_by_claim = engine.normalize(bundle.graph)
        deduplicated_graph, representatives_by_claim = engine.deduplicate(
            bundle.graph,
            keys_by_claim=keys_by_claim,
        )
        entity_resolutions, association_resolutions, link_resolutions = engine.resolve(
            deduplicated_graph,
            keys_by_claim=keys_by_claim,
            repositories=uow.repositories,
        )
        _ = (association_resolutions, link_resolutions)
        resolution = entity_resolutions[
            bundle.representative_entity_claim_id(
                incoming,
                representatives_by_claim=representatives_by_claim,
            )
        ]
        assert isinstance(resolution, ResolvedResolution)
        assert resolution.target.id == existing.id

        _, persistence = engine.reconcile(bundle.graph, uow=uow)
        assert persistence.persisted_entities == 0

    with sqlite_unit_of_work() as uow:
        persisted = uow.session.execute(select(Artist)).scalars().all()
        assert len(persisted) == 1


def test_reconciliation_matches_sidecar_keys(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    existing = Artist(name="Kendrick Lamar")
    engine = create_default_reconciliation_engine()
    seed_bundle = build_catalog_claim_graph(roots=(existing,), source=Provider.LASTFM)

    with sqlite_unit_of_work() as uow:
        _, persistence = engine.reconcile(seed_bundle.graph, uow=uow)
        assert persistence.persisted_entities == 1

    incoming = Artist(name="kendrick lamar")
    bundle = build_catalog_claim_graph(roots=(incoming,), source=Provider.SPOTIFY)

    with sqlite_unit_of_work() as uow:
        keys_by_claim = engine.normalize(bundle.graph)
        deduplicated_graph, representatives_by_claim = engine.deduplicate(
            bundle.graph,
            keys_by_claim=keys_by_claim,
        )
        entity_resolutions, association_resolutions, link_resolutions = engine.resolve(
            deduplicated_graph,
            keys_by_claim=keys_by_claim,
            repositories=uow.repositories,
        )
        _ = (association_resolutions, link_resolutions)
        resolution = entity_resolutions[
            bundle.representative_entity_claim_id(
                incoming,
                representatives_by_claim=representatives_by_claim,
            )
        ]
        assert isinstance(resolution, ResolvedResolution)
        assert resolution.target.id == existing.id
