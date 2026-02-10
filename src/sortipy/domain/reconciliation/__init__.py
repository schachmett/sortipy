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
    ClaimEvidence,
    ClaimMetadata,
    EntityClaim,
)
from .graph import ClaimGraph
from .plan import (
    ApplyInstruction,
    ApplyStrategy,
    CanonicalRef,
    EntityResolution,
    ResolutionPlan,
    ResolutionStatus,
)

__all__ = [
    "ApplyInstruction",
    "ApplyStrategy",
    "CanonicalRef",
    "ClaimEvidence",
    "ClaimGraph",
    "ClaimMetadata",
    "EntityClaim",
    "EntityResolution",
    "ResolutionPlan",
    "ResolutionStatus",
]
