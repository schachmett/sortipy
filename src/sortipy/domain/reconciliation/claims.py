"""Claim primitives used by reconciliation.

Claims wrap *real domain entities* with per-observation metadata.
This avoids tracking entity fields twice (once in the model, once in claims).

Important boundary rule:
- claim entities should be freshly built in adapters from provider payloads
- do not wrap repository-loaded ORM instances in claims

The domain layer does not enforce ORM/session state; adapter factories are
responsible for guarding this rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sortipy.domain.model import Entity

if TYPE_CHECKING:
    from uuid import UUID

    from sortipy.domain.model import EntityType, Provider


@dataclass(slots=True, kw_only=True)
class ClaimMetadata:
    """Metadata attached to a claim node for policy and audit decisions."""

    source: Provider
    confidence: float | None = None
    observed_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    ingest_event_id: str | None = None
    payload_hash: str | None = None
    notes: tuple[str, ...] = ()


@dataclass(slots=True, kw_only=True)
class ClaimEvidence:
    """Provider-specific evidence used by resolver/policy stages.

    This is *not* canonical domain state. It is auxiliary context for
    confidence/scoring decisions and audit diagnostics.
    """

    values: dict[str, object] = field(default_factory=dict["str", "object"])

    def get(self, key: str) -> object | None:
        return self.values.get(key)


@dataclass(slots=True, kw_only=True)
class EntityClaim[TEntity: Entity]:
    """Claim envelope for one observed domain entity state."""

    entity: TEntity
    metadata: ClaimMetadata
    evidence: ClaimEvidence = field(default_factory=ClaimEvidence)
    claim_id: UUID = field(default_factory=uuid4)

    @property
    def entity_type(self) -> EntityType:
        return self.entity.entity_type
