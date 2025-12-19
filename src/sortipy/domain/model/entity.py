"""
Base building blocks:
identity and canonicalization (resolved identity) semantics.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from sortipy.domain.model.enums import EntityType


def new_id() -> UUID:
    return uuid4()


@runtime_checkable
class EntityRef(Protocol):
    """Reference to a typed entity using its stable (resolved) identity."""

    @property
    def entity_type(self) -> EntityType: ...

    @property
    def resolved_id(self) -> UUID: ...


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
class CanonicalizableMixin(Entity, ABC):
    """Pointer-based canonicalization. Not tied to repositories or aggregate roots."""

    _canonical_id: UUID | None = field(default=None, init=False)

    @property
    def canonical_id(self) -> UUID | None:
        return self._canonical_id

    @property
    def is_canonical(self) -> bool:
        return self._canonical_id is None

    @property
    def resolved_id(self) -> UUID:
        """Return canonical/root id if present, else own id."""
        return self._canonical_id or self.id

    def clear_canonical(self) -> None:
        """Mark this entity as canonical (no pointer)."""
        self._canonical_id = None

    def point_to_canonical(self, canonical: EntityRef) -> None:
        """Point this entity at a canonical/root identity.

        This is the core domain operation for merge/canonicalization.
        """
        if canonical.entity_type != self.entity_type:
            raise ValueError("canonical target must have the same entity_type")
        canonical_id = canonical.resolved_id
        # Normalization: pointing at self means "no pointer".
        if canonical_id == self.id:
            self._canonical_id = None
            return
        self._canonical_id = canonical_id
