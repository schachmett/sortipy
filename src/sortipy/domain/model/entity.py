"""
Base building blocks:
identity and canonicalization (resolved identity) semantics.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, Protocol, cast, runtime_checkable
from uuid import uuid4

if TYPE_CHECKING:
    from collections.abc import Iterable
    from uuid import UUID

    from .enums import EntityType


def new_id() -> UUID:
    return uuid4()


@runtime_checkable
class IdentifiedEntity(Protocol):
    """Reference to a typed entity using its stable (resolved) identity."""

    @property
    def entity_type(self) -> EntityType: ...

    @property
    def resolved_id(self) -> UUID: ...


@dataclass(eq=False, kw_only=True)
class Entity:
    """Internal identity exists immediately in the domain."""

    id: UUID = field(default_factory=new_id)
    _changed_fields: set[str] = field(default_factory=set[str], repr=False, init=False)

    # class-level discriminator; subclasses must override
    ENTITY_TYPE: ClassVar[EntityType]

    @property
    def entity_type(self) -> EntityType:
        return self.ENTITY_TYPE

    @property
    def resolved_id(self) -> UUID:
        """Default: no canonicalization semantics"""
        return self.id

    def _ensure_changed_fields(self) -> set[str]:
        changed_fields = getattr(self, "_changed_fields", None)
        if changed_fields is None:
            changed_fields = set[str]()
            self._changed_fields = changed_fields
        return changed_fields

    def mark_changed(self, *fields: str) -> None:
        changed_fields = self._ensure_changed_fields()
        for field_name in fields:
            if not field_name:
                continue
            changed_fields.add(field_name)

    @property
    def changed_fields(self) -> frozenset[str]:
        return frozenset(self._ensure_changed_fields())

    @property
    def has_changes(self) -> bool:
        return bool(self._ensure_changed_fields())

    def clear_changed_fields(self) -> None:
        self._ensure_changed_fields().clear()

    def _set_field(self, field_name: str, value: object) -> None:
        if getattr(self, field_name) == value:
            return
        setattr(self, field_name, value)
        self.mark_changed(field_name)

    def _prefer_non_empty_string_field(self, field_name: str, incoming: str) -> None:
        if incoming.strip():
            self._set_field(field_name, incoming)

    def _prefer_optional_string_field(
        self,
        field_name: str,
        incoming: str | None,
    ) -> None:
        if incoming is None or not incoming.strip():
            return
        self._set_field(field_name, incoming)

    def _prefer_optional_value_field(self, field_name: str, incoming: object) -> None:
        if incoming is None:
            return
        self._set_field(field_name, incoming)

    def _merge_unique_list_field(
        self,
        field_name: str,
        incoming: Iterable[object],
    ) -> None:
        target = cast("list[object]", getattr(self, field_name))
        changed = False
        for item in incoming:
            if item in target:
                continue
            target.append(item)
            changed = True
        if changed:
            self.mark_changed(field_name)


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
        if self._canonical_id is None:
            return
        self._canonical_id = None
        self.mark_changed("canonical_id")

    def point_to_canonical(self, canonical: IdentifiedEntity) -> None:
        """Point this entity at a canonical/root identity.

        This is the core domain operation for merge/canonicalization.
        """
        if canonical.entity_type != self.entity_type:
            raise ValueError("canonical target must have the same entity_type")
        canonical_id = canonical.resolved_id
        # Normalization: pointing at self means "no pointer".
        if canonical_id == self.id:
            self.clear_canonical()
            return
        if self._canonical_id == canonical_id:
            return
        self._canonical_id = canonical_id
        self.mark_changed("canonical_id")
