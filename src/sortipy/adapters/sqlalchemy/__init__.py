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
    SqlAlchemyLibraryItemRepository,
    SqlAlchemyNormalizationSidecarRepository,
    SqlAlchemyPlayEventRepository,
    SqlAlchemyRecordingRepository,
    SqlAlchemyReleaseRepository,
    SqlAlchemyReleaseSetRepository,
    SqlAlchemyUserRepository,
)
from .unit_of_work import (
    SqlAlchemyUnitOfWork,
    startup,
)

__all__ = [
    "CLASS_BY_ENTITY_TYPE",
    "ENTITY_TYPE_BY_CLASS",
    "SqlAlchemyArtistRepository",
    "SqlAlchemyLibraryItemRepository",
    "SqlAlchemyNormalizationSidecarRepository",
    "SqlAlchemyPlayEventRepository",
    "SqlAlchemyRecordingRepository",
    "SqlAlchemyReleaseRepository",
    "SqlAlchemyReleaseSetRepository",
    "SqlAlchemyUnitOfWork",
    "SqlAlchemyUserRepository",
    "mapper_registry",
    "start_mappers",
    "startup",
]
