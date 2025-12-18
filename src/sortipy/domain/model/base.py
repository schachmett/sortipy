"""
Base building blocks:
identity, entity_type contract, resolvable canonicalization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, Protocol
from uuid import UUID, uuid4

from sortipy.domain.model.external_ids import ExternallyIdentifiableEntity
from sortipy.domain.model.provenance import IngestedEntity

if TYPE_CHECKING:
    from datetime import datetime

    from sortipy.domain.model.enums import EntityType


def new_id() -> UUID:
    return uuid4()


class HasEntityType(Protocol):
    """Structural contract for typed reference joins/dispatch."""

    ENTITY_TYPE: ClassVar[EntityType]

    @property
    def entity_type(self) -> EntityType: ...


@dataclass(eq=False, kw_only=True)
class Entity:
    """Internal identity exists immediately in the domain."""

    id: UUID = field(default_factory=new_id)

    # class-level discriminator; subclasses must override
    ENTITY_TYPE: ClassVar[EntityType]

    @property
    def entity_type(self) -> EntityType:
        return self.ENTITY_TYPE

    @property
    def resolved_id(self) -> UUID:
        """Default: no canonicalization semantics"""
        return self.id


@dataclass(eq=False, kw_only=True)
class ResolvableEntity(Entity):
    """Pointer-based canonicalization. Not tied to repositories or aggregate roots."""

    _canonical_id: UUID | None = None

    @property
    def canonical_id(self) -> UUID | None:
        return self._canonical_id

    @property
    def resolved_id(self) -> UUID:
        """Return canonical/root id if present, else own id."""
        return self._canonical_id or self.id


class IsMergable(Protocol):
    resolved_id: UUID


@dataclass(eq=False, kw_only=True)
class CanonicalEntity(ResolvableEntity, ExternallyIdentifiableEntity, IngestedEntity):
    """Canonical = resolvable + external ids + ingest trace.

    Aggregate root status is NOT implied.
    """

    updated_at: datetime | None = None
