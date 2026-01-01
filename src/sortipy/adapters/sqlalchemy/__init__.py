"""SQLAlchemy adapter package for Sortipy."""

from __future__ import annotations

from . import (
    sidecar_mappings as _sidecar_mappings,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)
from .mappings import (
    CLASS_BY_ENTITY_TYPE,
    ENTITY_TYPE_BY_CLASS,
    mapper_registry,
    start_mappers,
)
from .repositories import (
    SqlAlchemyArtistRepository,
    SqlAlchemyNormalizationSidecarRepository,
    SqlAlchemyPlayEventRepository,
    SqlAlchemyRecordingRepository,
    SqlAlchemyReleaseRepository,
    SqlAlchemyReleaseSetRepository,
)
from .unit_of_work import (
    SqlAlchemyIngestUnitOfWork,
    SqlAlchemyPlayEventUnitOfWork,
    startup,
)

__all__ = [
    "CLASS_BY_ENTITY_TYPE",
    "ENTITY_TYPE_BY_CLASS",
    "SqlAlchemyArtistRepository",
    "SqlAlchemyIngestUnitOfWork",
    "SqlAlchemyNormalizationSidecarRepository",
    "SqlAlchemyPlayEventRepository",
    "SqlAlchemyPlayEventUnitOfWork",
    "SqlAlchemyRecordingRepository",
    "SqlAlchemyReleaseRepository",
    "SqlAlchemyReleaseSetRepository",
    "mapper_registry",
    "start_mappers",
    "startup",
]
