"""SQLAlchemy adapter package for Sortipy."""

from __future__ import annotations

from .mappings import (
    CANONICAL_TYPE_BY_CLASS,
    CLASS_BY_CANONICAL_TYPE,
    create_all_tables,
    mapper_registry,
    start_mappers,
)
from .merger import CanonicalEntityMerger
from .repositories import SqlAlchemyPlayEventRepository
from .unit_of_work import SqlAlchemyUnitOfWork, get_unit_of_work, startup

__all__ = [
    "CANONICAL_TYPE_BY_CLASS",
    "CLASS_BY_CANONICAL_TYPE",
    "CanonicalEntityMerger",
    "SqlAlchemyPlayEventRepository",
    "SqlAlchemyUnitOfWork",
    "create_all_tables",
    "get_unit_of_work",
    "mapper_registry",
    "start_mappers",
    "startup",
]
