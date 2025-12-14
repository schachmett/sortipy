"""SQLAlchemy adapter package for Sortipy."""

from __future__ import annotations

from . import (
    sidecar_mappings as _sidecar_mappings,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)
from .mappings import (
    CANONICAL_TYPE_BY_CLASS,
    CLASS_BY_CANONICAL_TYPE,
    create_all_tables,
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
    SqlAlchemyTrackRepository,
)
from .unit_of_work import (
    SqlAlchemyIngestUnitOfWork,
    SqlAlchemyPlayEventUnitOfWork,
    startup,
)

__all__ = [
    "CANONICAL_TYPE_BY_CLASS",
    "CLASS_BY_CANONICAL_TYPE",
    "SqlAlchemyArtistRepository",
    "SqlAlchemyIngestUnitOfWork",
    "SqlAlchemyNormalizationSidecarRepository",
    "SqlAlchemyPlayEventRepository",
    "SqlAlchemyPlayEventUnitOfWork",
    "SqlAlchemyRecordingRepository",
    "SqlAlchemyReleaseRepository",
    "SqlAlchemyReleaseSetRepository",
    "SqlAlchemyTrackRepository",
    "create_all_tables",
    "mapper_registry",
    "start_mappers",
    "startup",
]
