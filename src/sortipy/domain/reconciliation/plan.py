"""Resolution plan types shared by resolver/policy/apply/persist stages.

The resolution plan is the contract between:
- identity resolution (read-only lookup)
- conflict/merge policy
- mutation/persistence orchestration

Keeping this model explicit prevents implicit coupling between pipeline phases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

    from sortipy.domain.model import EntityType, IdentifiedEntity


@dataclass(slots=True, kw_only=True)
class CanonicalRef:
    """Reference to a canonical entity selected by the resolver.

    ``entity`` is optional and may be attached by adapter-backed resolvers that
    already loaded ORM-backed instances. Reconciliation logic should primarily
    use ``entity_type`` + ``resolved_id`` as stable identity keys.
    """

    entity_type: EntityType
    resolved_id: UUID
    entity: IdentifiedEntity | None = None


class ResolutionStatus(StrEnum):
    """Outcome produced by identity resolution before policy refinement."""

    NEW = "new"
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    CONFLICT = "conflict"


@dataclass(slots=True, kw_only=True)
class EntityResolution:
    """Resolution result for a single claim node."""

    claim_id: UUID
    entity_type: EntityType
    status: ResolutionStatus
    target: CanonicalRef | None = None
    candidates: tuple[CanonicalRef, ...] = ()
    reason: str | None = None


class ApplyStrategy(StrEnum):
    """Policy decision on how to materialize one claim."""

    CREATE = "create"
    MERGE = "merge"
    SKIP = "skip"
    MANUAL_REVIEW = "manual_review"


@dataclass(slots=True, kw_only=True)
class ApplyInstruction:
    """Policy instruction for claim application/persistence stages."""

    claim_id: UUID
    strategy: ApplyStrategy
    target: CanonicalRef | None = None
    reason: str | None = None


@dataclass(slots=True)
class ResolutionPlan:
    """Aggregate plan for one reconciliation run."""

    resolutions: dict[UUID, EntityResolution] = field(
        default_factory=dict["UUID", "EntityResolution"]
    )
    instructions: list[ApplyInstruction] = field(default_factory=list["ApplyInstruction"])

    def add_resolution(self, resolution: EntityResolution) -> None:
        self.resolutions[resolution.claim_id] = resolution

    def resolution_for(self, claim_id: UUID) -> EntityResolution | None:
        return self.resolutions.get(claim_id)

    def add_instruction(self, instruction: ApplyInstruction) -> None:
        self.instructions.append(instruction)
