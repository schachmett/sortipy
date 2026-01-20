"""Audit records for canonicalization/merge decisions."""
# laterTODO add created_at, updated_at, etc?

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .enums import MergeReason

if TYPE_CHECKING:
    from uuid import UUID

    from .enums import EntityType


@dataclass(eq=False)
class EntityMerge:
    """Audit record for pointing a duplicate entity to its canonical counterpart."""

    entity_type: EntityType
    source_id: UUID
    target_id: UUID
    reason: MergeReason = MergeReason.MANUAL
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    created_by: str | None = None
