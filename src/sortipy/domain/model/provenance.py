from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from .entity import Entity

if TYPE_CHECKING:
    from uuid import UUID

    from .enums import EntityType, Provider


@dataclass(eq=False, kw_only=True)
class Provenance:
    _owner_type: EntityType | None = field(default=None, repr=False)
    _owner_id: UUID | None = field(default=None, repr=False)
    # TODO raw_payloads: list[Payload] | None = None # Payload class does not yet exist
    # TODO ingested_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    sources: set[Provider] = field(default_factory=set["Provider"], repr=False)

    @property
    def owner_type(self) -> EntityType | None:
        return self._owner_type

    @property
    def owner_id(self) -> UUID | None:
        return self._owner_id

    def set_owner(self, *, owner_type: EntityType, owner_id: UUID) -> None:
        self._owner_type = owner_type
        self._owner_id = owner_id


class Provenanced(Protocol):
    """Read-only access to provenance."""

    @property
    def provenance(self) -> Provenance | None: ...


class ProvenanceTracked(Provenanced, Protocol):
    """An entity that carries provenance and can mutate it."""

    def set_provenance(self, provenance: Provenance | None) -> None: ...

    def ensure_provenance(self) -> Provenance: ...

    def add_source(self, source: Provider) -> None: ...


@dataclass(eq=False, kw_only=True)
class ProvenanceTrackedMixin(Entity, ABC):
    """Capability: carries ingest provenance (optional)."""

    _provenance: Provenance | None = field(default=None, repr=False, init=False)

    @property
    def provenance(self) -> Provenance | None:
        return self._provenance

    def set_provenance(self, provenance: Provenance | None) -> None:
        self._provenance = provenance
        if provenance is not None and provenance.owner_type is None:
            provenance.set_owner(owner_type=self.entity_type, owner_id=self.id)

    def ensure_provenance(self) -> Provenance:
        if self._provenance is None:
            self._provenance = Provenance(_owner_type=self.entity_type, _owner_id=self.id)
        elif self._provenance.owner_type is None:
            self._provenance.set_owner(owner_type=self.entity_type, owner_id=self.id)
        return self._provenance

    def add_source(self, source: Provider) -> None:
        self.ensure_provenance().sources.add(source)
