from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sortipy.domain.model.enums import Provider


@dataclass(kw_only=True, eq=False)
class Provenance:
    # raw_payloads: list[Payload] | None = None # Payload class does not yet exist
    # ingested_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    sources: set[Provider] = field(default_factory=set["Provider"], repr=False)


@dataclass(eq=False, kw_only=True)
class IngestedEntity:
    """Mixin for ingests - replace with simple composition later"""

    provenance: Provenance | None = None


class HasIngestTrace(Protocol):
    provenance: Provenance | None
