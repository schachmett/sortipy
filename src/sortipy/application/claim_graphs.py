"""Application-local helpers for building catalog claim graphs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sortipy.domain.model import Artist, Label, Recording, Release, ReleaseSet
from sortipy.domain.reconciliation import (
    AssociationClaim,
    AssociationKind,
    ClaimGraph,
    ClaimMetadata,
    EntityClaim,
    LinkClaim,
    LinkKind,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sortipy.domain.model import AssociationEntity, CatalogEntity, Provider
    from sortipy.domain.reconciliation import ApplyResult, RepresentativesByClaim


def _representative_claim_id(
    claim_id: UUID,
    representatives_by_claim: RepresentativesByClaim,
) -> UUID:
    representative = representatives_by_claim.get(claim_id)
    while representative is not None:
        claim_id = representative.claim_id
        representative = representatives_by_claim.get(claim_id)
    return claim_id


@dataclass(slots=True)
class CatalogGraphBuildResult:
    """Claim graph plus object-identity lookup metadata for rebinding."""

    graph: ClaimGraph
    entity_claim_ids_by_object_id: dict[int, UUID]
    association_claim_ids_by_object_id: dict[int, UUID]

    def require_entity_claim_id(self, entity: CatalogEntity) -> UUID:
        try:
            return self.entity_claim_ids_by_object_id[id(entity)]
        except KeyError as exc:
            raise ValueError(f"Entity is not present in claim graph: {entity!r}") from exc

    def require_association_claim_id(self, association: AssociationEntity) -> UUID:
        try:
            return self.association_claim_ids_by_object_id[id(association)]
        except KeyError as exc:
            raise ValueError(f"Association is not present in claim graph: {association!r}") from exc

    def representative_entity_claim_id(
        self,
        entity: CatalogEntity,
        *,
        representatives_by_claim: RepresentativesByClaim,
    ) -> UUID:
        return _representative_claim_id(
            self.require_entity_claim_id(entity),
            representatives_by_claim,
        )

    def representative_association_claim_id(
        self,
        association: AssociationEntity,
        *,
        representatives_by_claim: RepresentativesByClaim,
    ) -> UUID:
        return _representative_claim_id(
            self.require_association_claim_id(association),
            representatives_by_claim,
        )

    def require_materialized_entity(
        self,
        entity: CatalogEntity,
        *,
        apply_result: ApplyResult,
        representatives_by_claim: RepresentativesByClaim,
    ) -> CatalogEntity:
        claim_id = self.representative_entity_claim_id(
            entity,
            representatives_by_claim=representatives_by_claim,
        )
        materialized = apply_result.entities_by_claim.get(claim_id)
        if materialized is None:
            raise ValueError(f"No materialized entity for claim {claim_id}")
        if not isinstance(materialized, Artist | Label | Recording | Release | ReleaseSet):
            raise TypeError(
                f"Materialized entity is not a catalog entity: {type(materialized).__name__}"
            )
        return materialized

    def require_materialized_association(
        self,
        association: AssociationEntity,
        *,
        apply_result: ApplyResult,
        representatives_by_claim: RepresentativesByClaim,
    ) -> AssociationEntity:
        claim_id = self.representative_association_claim_id(
            association,
            representatives_by_claim=representatives_by_claim,
        )
        materialized = apply_result.associations_by_claim.get(claim_id)
        if materialized is None:
            raise ValueError(f"No materialized association for claim {claim_id}")
        return materialized


class _CatalogClaimGraphBuilder:
    def __init__(self, *, source: Provider) -> None:
        self._metadata = ClaimMetadata(source=source)
        self._graph = ClaimGraph()
        self._entity_claim_ids: dict[int, UUID] = {}
        self._association_claim_ids: dict[int, UUID] = {}
        self._visited_entity_ids: set[int] = set()
        self._link_keys: set[tuple[LinkKind, UUID, UUID]] = set()

    def build(self, roots: tuple[CatalogEntity, ...]) -> CatalogGraphBuildResult:
        for root in roots:
            claim_id = self._visit_catalog_entity(root)
            self._graph.add_root(self._graph.require_claim(claim_id))
        self._graph.validate_invariants()
        return CatalogGraphBuildResult(
            graph=self._graph,
            entity_claim_ids_by_object_id=dict(self._entity_claim_ids),
            association_claim_ids_by_object_id=dict(self._association_claim_ids),
        )

    def _visit_catalog_entity(self, entity: CatalogEntity) -> UUID:
        claim_id = self._ensure_entity_claim(entity)
        entity_key = id(entity)
        if entity_key in self._visited_entity_ids:
            return claim_id
        self._visited_entity_ids.add(entity_key)

        match entity:
            case Artist() | Label():
                return claim_id
            case ReleaseSet():
                self._visit_release_set(entity)
                return claim_id
            case Release():
                self._visit_release(entity)
                return claim_id
            case Recording():
                self._visit_recording(entity)
                return claim_id

    def _visit_release_set(self, release_set: ReleaseSet) -> None:
        release_set_claim_id = self._ensure_entity_claim(release_set)
        for contribution in release_set.contributions:
            artist_claim_id = self._visit_catalog_entity(contribution.artist)
            self._ensure_association_claim(
                contribution,
                kind=AssociationKind.RELEASE_SET_CONTRIBUTION,
                source_claim_id=release_set_claim_id,
                target_claim_id=artist_claim_id,
            )
        for release in release_set.releases:
            release_claim_id = self._visit_catalog_entity(release)
            self._ensure_link_claim(
                kind=LinkKind.RELEASE_SET_RELEASE,
                source_claim_id=release_set_claim_id,
                target_claim_id=release_claim_id,
            )

    def _visit_release(self, release: Release) -> None:
        release_claim_id = self._ensure_entity_claim(release)
        release_set_claim_id = self._visit_catalog_entity(release.release_set)
        self._ensure_link_claim(
            kind=LinkKind.RELEASE_SET_RELEASE,
            source_claim_id=release_set_claim_id,
            target_claim_id=release_claim_id,
        )
        for label in release.labels:
            label_claim_id = self._visit_catalog_entity(label)
            self._ensure_link_claim(
                kind=LinkKind.RELEASE_LABEL,
                source_claim_id=release_claim_id,
                target_claim_id=label_claim_id,
            )
        for track in release.tracks:
            recording_claim_id = self._visit_catalog_entity(track.recording)
            self._ensure_association_claim(
                track,
                kind=AssociationKind.RELEASE_TRACK,
                source_claim_id=release_claim_id,
                target_claim_id=recording_claim_id,
            )

    def _visit_recording(self, recording: Recording) -> None:
        recording_claim_id = self._ensure_entity_claim(recording)
        for contribution in recording.contributions:
            artist_claim_id = self._visit_catalog_entity(contribution.artist)
            self._ensure_association_claim(
                contribution,
                kind=AssociationKind.RECORDING_CONTRIBUTION,
                source_claim_id=recording_claim_id,
                target_claim_id=artist_claim_id,
            )
        for track in recording.release_tracks:
            release_claim_id = self._visit_catalog_entity(track.release)
            self._ensure_association_claim(
                track,
                kind=AssociationKind.RELEASE_TRACK,
                source_claim_id=release_claim_id,
                target_claim_id=recording_claim_id,
            )

    def _ensure_entity_claim(self, entity: CatalogEntity) -> UUID:
        key = id(entity)
        claim_id = self._entity_claim_ids.get(key)
        if claim_id is not None:
            return claim_id
        claim = EntityClaim(entity=entity, metadata=self._metadata)
        self._graph.add(claim)
        self._entity_claim_ids[key] = claim.claim_id
        return claim.claim_id

    def _ensure_association_claim(
        self,
        association: AssociationEntity,
        *,
        kind: AssociationKind,
        source_claim_id: UUID,
        target_claim_id: UUID,
    ) -> UUID:
        key = id(association)
        claim_id = self._association_claim_ids.get(key)
        if claim_id is not None:
            return claim_id
        claim = AssociationClaim(
            source_claim_id=source_claim_id,
            target_claim_id=target_claim_id,
            kind=kind,
            metadata=self._metadata,
            payload=association,
        )
        self._graph.add_relationship(claim)
        self._association_claim_ids[key] = claim.claim_id
        return claim.claim_id

    def _ensure_link_claim(
        self,
        *,
        kind: LinkKind,
        source_claim_id: UUID,
        target_claim_id: UUID,
    ) -> None:
        link_key = (kind, source_claim_id, target_claim_id)
        if link_key in self._link_keys:
            return
        self._link_keys.add(link_key)
        self._graph.add_relationship(
            LinkClaim(
                source_claim_id=source_claim_id,
                target_claim_id=target_claim_id,
                kind=kind,
                metadata=self._metadata,
            )
        )


def build_catalog_claim_graph(
    *,
    roots: tuple[CatalogEntity, ...],
    source: Provider,
) -> CatalogGraphBuildResult:
    """Build a claim graph rooted at fresh catalog aggregates."""

    return _CatalogClaimGraphBuilder(source=source).build(roots)
