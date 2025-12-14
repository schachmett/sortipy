from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session  # noqa: TC002

from sortipy.adapters.sqlalchemy.repositories import SqlAlchemyNormalizationSidecarRepository
from sortipy.adapters.sqlalchemy.sidecar_mappings import normalization_sidecar_table
from sortipy.domain.ingest_pipeline.state import NormalizationData
from sortipy.domain.types import Artist, CanonicalEntity, CanonicalEntityType


@dataclass(slots=True)
class _Data(NormalizationData[CanonicalEntity]):
    priority_keys: tuple[tuple[object, ...], ...]


def test_save_and_find_by_keys(sqlite_session: Session) -> None:
    normalization_sidecar_table.create(sqlite_session.get_bind(), checkfirst=True)
    repo = SqlAlchemyNormalizationSidecarRepository(sqlite_session)
    artist = Artist(name="Radiohead")
    artist.id = uuid.uuid4()
    sqlite_session.add(artist)
    data = _Data(priority_keys=(("artist:mbid", "mbid-1"), ("artist:name", "radiohead"),))

    repo.save(artist, data)
    sqlite_session.flush()
    rows = sqlite_session.execute(normalization_sidecar_table.select()).all()
    assert len(rows) == 2

    found = repo.find_by_keys(
        CanonicalEntityType.ARTIST,
        (("artist:mbid", "mbid-1"), ("artist:name", "radiohead")),
    )

    assert len(found) == 2
    assert found[("artist:mbid", "mbid-1")] is artist
    assert found[("artist:name", "radiohead")] is artist


def test_save_ignores_empty_keys(sqlite_session: Session) -> None:
    normalization_sidecar_table.create(sqlite_session.get_bind(), checkfirst=True)
    repo = SqlAlchemyNormalizationSidecarRepository(sqlite_session)
    artist = Artist(name="Empty")
    artist.id = uuid.uuid4()
    data = _Data(priority_keys=())

    repo.save(artist, data)
    sqlite_session.flush()

    found = repo.find_by_keys(CanonicalEntityType.ARTIST, (("artist:name", "empty"),))
    assert found == {}
