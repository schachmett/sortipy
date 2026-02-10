"""Claim graph containers used by reconciliation services.

The claim graph is intentionally explicit and mutable:
- adapters append claim nodes as they translate provider payloads
- normalization/resolution stages consume these lists in deterministic order
- deduplication can collapse claim nodes and rewrite root collections

The first draft keeps one unified graph type for both catalog and user-centric
workflows; if needed, this can later be split into specialized graph variants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sortipy.domain.model import EntityType

if TYPE_CHECKING:
    from uuid import UUID

    from sortipy.domain.model import Entity

    from .claims import EntityClaim


def _new_claim_index() -> dict[EntityType, list[UUID]]:
    return {entity_type: [] for entity_type in EntityType}


@dataclass(slots=True)
class ClaimGraph:
    """Container for one reconciliation run.

    ``roots`` contains entry claims that define workflow intent. All claims are
    indexed by ``entity_type`` for deterministic per-type resolver processing.
    """

    _claims_by_id: dict[UUID, EntityClaim[Entity]] = field(
        default_factory=dict["UUID", "EntityClaim[Entity]"], repr=False
    )
    _root_ids: list[UUID] = field(default_factory=list["UUID"], repr=False)
    _claim_ids_by_entity_type: dict[EntityType, list[UUID]] = field(
        default_factory=_new_claim_index,
        repr=False,
    )

    @property
    def claims(self) -> tuple[EntityClaim[Entity], ...]:
        return tuple(self._claims_by_id.values())

    @property
    def roots(self) -> tuple[EntityClaim[Entity], ...]:
        return tuple(self._claims_by_id[claim_id] for claim_id in self._root_ids)

    def add(self, claim: EntityClaim[Entity], *, root: bool = False) -> None:
        existing = self._claims_by_id.get(claim.claim_id)
        if existing is None:
            self._claims_by_id[claim.claim_id] = claim
            self._claim_ids_by_entity_type[claim.entity_type].append(claim.claim_id)
        if root and claim.claim_id not in self._root_ids:
            self._root_ids.append(claim.claim_id)

    def add_root(self, claim: EntityClaim[Entity]) -> None:
        self.add(claim, root=True)

    def claim_for(self, claim_id: UUID) -> EntityClaim[Entity] | None:
        return self._claims_by_id.get(claim_id)

    def claims_for(self, entity_type: EntityType) -> tuple[EntityClaim[Entity], ...]:
        claim_ids = self._claim_ids_by_entity_type[entity_type]
        return tuple(self._claims_by_id[claim_id] for claim_id in claim_ids)
