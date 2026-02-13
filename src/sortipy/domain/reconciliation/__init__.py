"""Reconciliation core for integrating external claim graphs into the catalog.

This package is the target replacement for the current split between
``domain.ingest_pipeline`` and ``domain.entity_updates``.

Planned layered flow:
1) build a claim graph from adapter payloads
2) normalize claim keys
3) deduplicate claims intra-batch
4) resolve canonical targets from persistence ports
5) apply conflict/merge policy
6) apply decisions to domain entities
7) persist changes and provenance events
"""

from __future__ import annotations

from .claims import (
    CatalogEntity,
    ClaimEvidence,
    ClaimMetadata,
    EntityClaim,
    RelationshipClaim,
    RelationshipKind,
    UserEntity,
)
from .contracts import (
    AmbiguousEntityResolution,
    ApplyInstruction,
    ApplyStrategy,
    ClaimKey,
    ConflictEntityResolution,
    EntityResolution,
    InstructionsByClaim,
    KeysByClaim,
    MatchKind,
    NewEntityResolution,
    Representative,
    RepresentativesByClaim,
    ResolutionsByClaim,
    ResolutionStatus,
    ResolvedEntityResolution,
)
from .graph import ClaimGraph

__all__ = [
    "AmbiguousEntityResolution",
    "ApplyInstruction",
    "ApplyStrategy",
    "CatalogEntity",
    "ClaimEvidence",
    "ClaimGraph",
    "ClaimKey",
    "ClaimMetadata",
    "ConflictEntityResolution",
    "EntityClaim",
    "EntityResolution",
    "InstructionsByClaim",
    "KeysByClaim",
    "MatchKind",
    "NewEntityResolution",
    "RelationshipClaim",
    "RelationshipKind",
    "Representative",
    "RepresentativesByClaim",
    "ResolutionStatus",
    "ResolutionsByClaim",
    "ResolvedEntityResolution",
    "UserEntity",
]
