"""Shared reconciliation contract components.

This module intentionally holds only:
- claim-key and ``*ByClaim`` mapping aliases
- generic resolution/instruction dataclasses and enums
"""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from sortipy.domain.model import EntityType

from .claims import AssociationKind, ClaimEntity, LinkKind, RelationshipClaimEntity

if TYPE_CHECKING:
    from sortipy.domain.model import IdentifiedEntity


### normalization contracts

type ClaimKey = tuple[Hashable, ...]
type KeysByClaim = dict[UUID, tuple[ClaimKey, ...]]


### deduplication contracts


@dataclass(slots=True, kw_only=True)
class Representative:
    """Representative produced by intra-batch deduplication."""

    claim_id: UUID
    matched_key: ClaimKey | None = None


type RepresentativesByClaim = dict[UUID, Representative]


### resolution contracts


class ResolutionStatus(StrEnum):
    """Outcome produced by identity resolution before policy refinement."""

    NEW = "new"
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    CONFLICT = "conflict"
    BLOCKED = "blocked"


class MatchKind(StrEnum):
    """How a resolver matched a claim against canonical candidates."""

    EXACT = "exact"
    FUZZY = "fuzzy"
    HEURISTIC = "heuristic"


@dataclass(slots=True, kw_only=True)
class NewResolution:
    """Claim has no canonical match and should be created."""

    status: Literal[ResolutionStatus.NEW] = ResolutionStatus.NEW
    reason: str | None = None


@dataclass(slots=True, kw_only=True)
class ResolvedResolution[TEntity: IdentifiedEntity]:
    """Claim resolved to one canonical target."""

    target: TEntity
    match_kind: MatchKind | None = None
    confidence: float | None = None
    matched_key: ClaimKey | None = None
    reason: str | None = None
    status: Literal[ResolutionStatus.RESOLVED] = ResolutionStatus.RESOLVED


@dataclass(slots=True, kw_only=True)
class AmbiguousResolution[TEntity: IdentifiedEntity]:
    """Claim matched multiple viable canonical candidates."""

    candidates: tuple[TEntity, ...]
    match_kind: MatchKind | None = None
    confidence: float | None = None
    matched_key: ClaimKey | None = None
    reason: str | None = None
    status: Literal[ResolutionStatus.AMBIGUOUS] = ResolutionStatus.AMBIGUOUS

    def __post_init__(self) -> None:
        if not self.candidates:
            raise ValueError("Ambiguous resolution must include at least one candidate")


@dataclass(slots=True, kw_only=True)
class ConflictResolution[TEntity: IdentifiedEntity]:
    """Claim has conflicting candidate set and cannot be auto-resolved."""

    candidates: tuple[TEntity, ...] = ()
    match_kind: MatchKind | None = None
    confidence: float | None = None
    matched_key: ClaimKey | None = None
    reason: str | None = None
    status: Literal[ResolutionStatus.CONFLICT] = ResolutionStatus.CONFLICT


@dataclass(slots=True, kw_only=True)
class BlockedResolution:
    """Claim is blocked by unresolved dependencies."""

    blocked_by_claim_ids: tuple[UUID, ...]
    status: Literal[ResolutionStatus.BLOCKED] = ResolutionStatus.BLOCKED
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.blocked_by_claim_ids:
            raise ValueError("Blocked resolution must include blocked claim IDs")


@dataclass(slots=True, kw_only=True)
class LinkResolvedResolution:
    """Link claim resolved by endpoint link existence, no target payload needed."""

    status: Literal[ResolutionStatus.RESOLVED] = ResolutionStatus.RESOLVED
    reason: str | None = None


@dataclass(slots=True, kw_only=True)
class LinkConflictResolution:
    """Link claim cannot be resolved due to incompatible endpoint state."""

    status: Literal[ResolutionStatus.CONFLICT] = ResolutionStatus.CONFLICT
    reason: str | None = None


type EntityResolution = (
    NewResolution
    | ResolvedResolution[ClaimEntity]
    | AmbiguousResolution[ClaimEntity]
    | ConflictResolution[ClaimEntity]
)
type EntityResolutionsByClaim = dict[UUID, EntityResolution]

type AssociationResolution = (
    NewResolution
    | ResolvedResolution[RelationshipClaimEntity]
    | AmbiguousResolution[RelationshipClaimEntity]
    | ConflictResolution[RelationshipClaimEntity]
    | BlockedResolution
)
type AssociationResolutionsByClaim = dict[UUID, AssociationResolution]

type LinkResolution = (
    NewResolution | LinkResolvedResolution | LinkConflictResolution | BlockedResolution
)
type LinkResolutionsByClaim = dict[UUID, LinkResolution]


### apply contracts


class ApplyStrategy(StrEnum):
    """Policy decision on how to materialize one claim."""

    CREATE = "create"
    MERGE = "merge"
    NOOP = "noop"
    MANUAL_REVIEW = "manual_review"


@dataclass(slots=True, kw_only=True)
class CreateInstruction:
    """Instruction to create one new target object."""

    strategy: Literal[ApplyStrategy.CREATE] = ApplyStrategy.CREATE
    reason: str | None = None


@dataclass(slots=True, kw_only=True)
class MergeInstruction[TEntity: IdentifiedEntity]:
    """Instruction to merge incoming state into an existing target."""

    target: TEntity
    strategy: Literal[ApplyStrategy.MERGE] = ApplyStrategy.MERGE
    reason: str | None = None


@dataclass(slots=True, kw_only=True)
class NoopInstruction[TEntity: IdentifiedEntity]:
    """Instruction that intentionally performs no mutation."""

    strategy: Literal[ApplyStrategy.NOOP] = ApplyStrategy.NOOP
    target: TEntity | None = None
    reason: str | None = None


@dataclass(slots=True, kw_only=True)
class ManualReviewInstruction:
    """Instruction deferred to manual review."""

    strategy: Literal[ApplyStrategy.MANUAL_REVIEW] = ApplyStrategy.MANUAL_REVIEW
    blocked_by_claim_ids: tuple[UUID, ...] = ()
    candidate_entity_ids: tuple[UUID, ...] = ()
    reason: str | None = None


@dataclass(slots=True, kw_only=True)
class LinkCreateInstruction:
    """Instruction to create a payload-free link."""

    strategy: Literal[ApplyStrategy.CREATE] = ApplyStrategy.CREATE
    reason: str | None = None


@dataclass(slots=True, kw_only=True)
class LinkNoopInstruction:
    """Instruction to keep existing link unchanged."""

    strategy: Literal[ApplyStrategy.NOOP] = ApplyStrategy.NOOP
    reason: str | None = None


@dataclass(slots=True, kw_only=True)
class LinkManualReviewInstruction:
    """Instruction for payload-free links requiring manual handling."""

    strategy: Literal[ApplyStrategy.MANUAL_REVIEW] = ApplyStrategy.MANUAL_REVIEW
    blocked_by_claim_ids: tuple[UUID, ...] = ()
    candidate_entity_ids: tuple[UUID, ...] = ()
    reason: str | None = None


class ManualReviewSubject(StrEnum):
    """Claim shape associated with one manual review item."""

    ENTITY = "entity"
    ASSOCIATION = "association"
    LINK = "link"


type ManualReviewKind = EntityType | AssociationKind | LinkKind


@dataclass(slots=True, kw_only=True)
class ManualReviewItem:
    """Artifact emitted by apply for follow-up manual reconciliation."""

    claim_id: UUID
    subject: ManualReviewSubject
    kind: ManualReviewKind
    blocked_by_claim_ids: tuple[UUID, ...] = ()
    candidate_entity_ids: tuple[UUID, ...] = ()
    reason: str | None = None


type EntityApplyInstruction = (
    CreateInstruction
    | MergeInstruction[IdentifiedEntity]
    | NoopInstruction[IdentifiedEntity]
    | ManualReviewInstruction
)
type EntityInstructionsByClaim = dict[UUID, EntityApplyInstruction]

type AssociationApplyInstruction = (
    CreateInstruction
    | MergeInstruction[RelationshipClaimEntity]
    | NoopInstruction[RelationshipClaimEntity]
    | ManualReviewInstruction
)
type AssociationInstructionsByClaim = dict[UUID, AssociationApplyInstruction]

type LinkApplyInstruction = (
    LinkCreateInstruction | LinkNoopInstruction | LinkManualReviewInstruction
)
type LinkInstructionsByClaim = dict[UUID, LinkApplyInstruction]
