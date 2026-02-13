"""Shared reconciliation contract components.

This module intentionally holds only:
- claim-key and ``*ByClaim`` mapping aliases
- component dataclasses/enums used inside those mappings
"""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Literal
from uuid import UUID

if TYPE_CHECKING:
    from sortipy.domain.model import IdentifiedEntity


type ClaimKey = tuple[Hashable, ...]
type KeysByClaim = dict[UUID, tuple[ClaimKey, ...]]


@dataclass(slots=True, kw_only=True)
class Representative:
    """Representative produced by intra-batch deduplication."""

    claim_id: UUID
    matched_key: ClaimKey | None = None


type RepresentativesByClaim = dict[UUID, Representative]


class ResolutionStatus(StrEnum):
    """Outcome produced by identity resolution before policy refinement."""

    NEW = "new"
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    CONFLICT = "conflict"


class MatchKind(StrEnum):
    """How a resolver matched a claim against canonical candidates."""

    EXACT = "exact"
    FUZZY = "fuzzy"
    HEURISTIC = "heuristic"


@dataclass(slots=True, kw_only=True)
class NewEntityResolution:
    """Claim has no canonical match and should be created."""

    status: Literal[ResolutionStatus.NEW] = ResolutionStatus.NEW
    reason: str | None = None


@dataclass(slots=True, kw_only=True)
class ResolvedEntityResolution:
    """Claim resolved to one canonical target."""

    target: IdentifiedEntity
    match_kind: MatchKind
    confidence: float | None = None
    matched_key: ClaimKey | None = None
    reason: str | None = None
    status: Literal[ResolutionStatus.RESOLVED] = ResolutionStatus.RESOLVED


@dataclass(slots=True, kw_only=True)
class AmbiguousEntityResolution:
    """Claim matched multiple viable canonical candidates."""

    candidates: tuple[IdentifiedEntity, ...]
    match_kind: MatchKind | None = None
    confidence: float | None = None
    matched_key: ClaimKey | None = None
    reason: str | None = None
    status: Literal[ResolutionStatus.AMBIGUOUS] = ResolutionStatus.AMBIGUOUS

    def __post_init__(self) -> None:
        if not self.candidates:
            raise ValueError("Ambiguous resolution must include at least one candidate")


@dataclass(slots=True, kw_only=True)
class ConflictEntityResolution:
    """Claim has conflicting candidate set and cannot be auto-resolved."""

    candidates: tuple[IdentifiedEntity, ...]
    match_kind: MatchKind | None = None
    confidence: float | None = None
    matched_key: ClaimKey | None = None
    reason: str | None = None
    status: Literal[ResolutionStatus.CONFLICT] = ResolutionStatus.CONFLICT

    def __post_init__(self) -> None:
        if not self.candidates:
            raise ValueError("Conflict resolution must include at least one candidate")


type EntityResolution = (
    NewEntityResolution
    | ResolvedEntityResolution
    | AmbiguousEntityResolution
    | ConflictEntityResolution
)
type ResolutionsByClaim = dict[UUID, EntityResolution]


class ApplyStrategy(StrEnum):
    """Policy decision on how to materialize one claim."""

    CREATE = "create"
    MERGE = "merge"
    NOOP = "noop"
    MANUAL_REVIEW = "manual_review"


@dataclass(slots=True, kw_only=True)
class ApplyInstruction:
    """Policy instruction for claim application/persistence stages."""

    strategy: ApplyStrategy
    target: IdentifiedEntity | None = None
    reason: str | None = None


type InstructionsByClaim = dict[UUID, ApplyInstruction]
