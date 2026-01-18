"""SQLAlchemy metadata for ingest normalization sidecars."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, Enum, Index, String, Table, UniqueConstraint

from sortipy.domain.model import EntityType

from .mappings import UUIDColumnType, mapper_registry

normalization_sidecar_table = Table(
    "normalization_sidecar",
    mapper_registry.metadata,
    Column("id", UUIDColumnType, primary_key=True, default=uuid.uuid4),
    Column("entity_type", Enum(EntityType, native_enum=False), nullable=False),
    Column("entity_id", UUIDColumnType, nullable=False),
    Column("key", String, nullable=False),
    UniqueConstraint("entity_type", "key"),
    Index("ix_normalization_sidecar_entity_key", "entity_type", "key"),
)
