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

from .claims import AssociationClaim, AssociationKind, LinkClaim, LinkKind

if TYPE_CHECKING:
    from uuid import UUID

    from .claims import AnyRelationshipClaim, EntityClaim, RelationshipKind


def _new_relationship_index() -> dict[RelationshipKind, list[UUID]]:
    return {kind: [] for kind in (*tuple(AssociationKind), *tuple(LinkKind))}


@dataclass(slots=True)
class ClaimGraph:
    """Container for one reconciliation run.

    ``roots`` contains entry claims that define workflow intent. All claims are
    indexed by ``entity_type`` for deterministic per-type resolver processing.
    """

    _entity_claims_by_id: dict[UUID, EntityClaim] = field(
        default_factory=dict["UUID", "EntityClaim"], repr=False
    )
    _root_entity_claim_ids: list[UUID] = field(default_factory=list["UUID"], repr=False)
    _relationship_claims_by_id: dict[UUID, AnyRelationshipClaim] = field(
        default_factory=dict["UUID", "AnyRelationshipClaim"], repr=False
    )
    _relationship_claim_ids_by_kind: dict[RelationshipKind, list[UUID]] = field(
        default_factory=_new_relationship_index,
        repr=False,
    )

    @property
    def claims(self) -> tuple[EntityClaim, ...]:
        return tuple(self._entity_claims_by_id.values())

    @property
    def roots(self) -> tuple[EntityClaim, ...]:
        return tuple(
            self._entity_claims_by_id[claim_id] for claim_id in self._root_entity_claim_ids
        )

    @property
    def relationships(self) -> tuple[AnyRelationshipClaim, ...]:
        return tuple(self._relationship_claims_by_id.values())

    def add(self, claim: EntityClaim, *, root: bool = False) -> None:
        existing = self._entity_claims_by_id.get(claim.claim_id)
        if existing is None:
            self._entity_claims_by_id[claim.claim_id] = claim
        if root and claim.claim_id not in self._root_entity_claim_ids:
            self._root_entity_claim_ids.append(claim.claim_id)

    def add_root(self, claim: EntityClaim) -> None:
        self.add(claim, root=True)

    def add_relationship(self, claim: AnyRelationshipClaim) -> None:
        self._assert_entity_claim_exists(claim.source_claim_id, role="source")
        self._assert_entity_claim_exists(claim.target_claim_id, role="target")

        existing = self._relationship_claims_by_id.get(claim.claim_id)
        if existing is None:
            self._relationship_claims_by_id[claim.claim_id] = claim
            self._relationship_claim_ids_by_kind[claim.kind].append(claim.claim_id)

    def claim_for(self, claim_id: UUID) -> EntityClaim | None:
        return self._entity_claims_by_id.get(claim_id)

    def relationship_for(self, claim_id: UUID) -> AnyRelationshipClaim | None:
        return self._relationship_claims_by_id.get(claim_id)

    def require_claim(self, claim_id: UUID) -> EntityClaim:
        """Return claim or raise when ``claim_id`` is unknown."""

        claim = self.claim_for(claim_id)
        if claim is None:
            msg = f"Unknown claim {claim_id}"
            raise ValueError(msg)
        return claim

    def require_relationship(self, claim_id: UUID) -> AnyRelationshipClaim:
        """Return relationship claim or raise when ``claim_id`` is unknown."""

        relationship = self.relationship_for(claim_id)
        if relationship is None:
            msg = f"Unknown relationship claim {claim_id}"
            raise ValueError(msg)
        return relationship

    def require_association(self, claim_id: UUID) -> AssociationClaim:
        """Return association claim or raise on unknown/invalid claim type."""

        relationship = self.require_relationship(claim_id)
        if not isinstance(relationship, AssociationClaim):
            msg = f"Expected association claim for {claim_id}, got {type(relationship).__name__}"
            raise TypeError(msg)
        return relationship

    def require_link(self, claim_id: UUID) -> LinkClaim:
        """Return link claim or raise on unknown/invalid claim type."""

        relationship = self.require_relationship(claim_id)
        if not isinstance(relationship, LinkClaim):
            msg = f"Expected link claim for {claim_id}, got {type(relationship).__name__}"
            raise TypeError(msg)
        return relationship

    def relationships_for(self, kind: RelationshipKind) -> tuple[AnyRelationshipClaim, ...]:
        claim_ids = self._relationship_claim_ids_by_kind[kind]
        return tuple(self._relationship_claims_by_id[claim_id] for claim_id in claim_ids)

    def validate_invariants(self) -> None:
        for claim_id in self._root_entity_claim_ids:
            self._assert_entity_claim_exists(claim_id, role="root")

        for kind, claim_ids in self._relationship_claim_ids_by_kind.items():
            for claim_id in claim_ids:
                relationship = self._relationship_claims_by_id.get(claim_id)
                if relationship is None:
                    raise ValueError(
                        f"Relationship claim index references missing claim {claim_id}"
                    )
                if relationship.kind is not kind:
                    raise ValueError(
                        f"Relationship kind index mismatch for {claim_id}: "
                        f"{relationship.kind} != {kind}"
                    )
                self._assert_entity_claim_exists(relationship.source_claim_id, role="source")
                self._assert_entity_claim_exists(relationship.target_claim_id, role="target")

    def _assert_entity_claim_exists(self, claim_id: UUID, *, role: str) -> None:
        if claim_id not in self._entity_claims_by_id:
            raise ValueError(f"Entity claim does not exist for {role}: {claim_id}")
