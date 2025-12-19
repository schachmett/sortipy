from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from sortipy.domain.model.entity import Entity

if TYPE_CHECKING:
    from sortipy.domain.model.enums import Provider


@dataclass(eq=False, kw_only=True)
class Provenance:
    # raw_payloads: list[Payload] | None = None # Payload class does not yet exist
    # ingested_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    sources: set[Provider] = field(default_factory=set["Provider"], repr=False)


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

    def ensure_provenance(self) -> Provenance:
        if self._provenance is None:
            self._provenance = Provenance()
        return self._provenance

    def add_source(self, source: Provider) -> None:
        self.ensure_provenance().sources.add(source)
