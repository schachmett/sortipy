"""Normalization stage contracts for claim reconciliation.

Responsibilities of this stage:
- derive deterministic lookup keys from claims
- expose keys per claim node (not per canonical entity)
- avoid persistence side effects

Implementation note:
- key strategies currently live in ``domain.ingest_pipeline.entity_ops``
- this module is the target destination for claim-based equivalents
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from uuid import UUID

    from .graph import ClaimGraph


type ClaimKey = tuple[object, ...]


@dataclass(slots=True)
class NormalizationResult:
    """Deterministic keys for every claim in the graph."""

    keys_by_claim: dict[UUID, tuple[ClaimKey, ...]]


class ClaimNormalizer(Protocol):
    """Compute deterministic keys for a claim graph."""

    def normalize(self, graph: ClaimGraph) -> NormalizationResult: ...
