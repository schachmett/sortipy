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

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Self
from uuid import uuid4

from sortipy.domain.model import (
    CatalogEntity,
    LibraryItem,
    PlayEvent,
    RecordingContribution,
    ReleaseSetContribution,
    ReleaseTrack,
    User,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sortipy.domain.model import (
        AssociationEntity,
        EntityType,
        Provider,
    )


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


type UserEntity = LibraryItem | PlayEvent | User
type ClaimEntity = CatalogEntity | UserEntity
_ASSOCIATION_ENTITY_TYPES = (RecordingContribution, ReleaseSetContribution, ReleaseTrack)
type RelationshipClaimEntity = AssociationEntity


@dataclass(slots=True, kw_only=True)
class EntityClaim:
    """Claim envelope for one observed domain entity state."""

    entity: ClaimEntity
    metadata: ClaimMetadata
    evidence: ClaimEvidence = field(default_factory=ClaimEvidence)
    claim_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if isinstance(self.entity, _ASSOCIATION_ENTITY_TYPES):
            raise TypeError("Association entities must be modeled as relationship claims.")

    @property
    def entity_type(self) -> EntityType:
        return self.entity.entity_type


class AssociationKind(StrEnum):
    """Kinds for payload-bearing n:m association claims."""

    RELEASE_SET_CONTRIBUTION = "release_set_contribution"
    RECORDING_CONTRIBUTION = "recording_contribution"
    RELEASE_TRACK = "release_track"


class LinkKind(StrEnum):
    """Kinds for payload-free link claims."""

    RELEASE_LABEL = "release_label"
    RELEASE_SET_RELEASE = "release_set_release"
    USER_LIBRARY_ITEM = "user_library_item"
    USER_PLAY_EVENT = "user_play_event"


type RelationshipKind = AssociationKind | LinkKind


@dataclass(slots=True, kw_only=True)
class _RelationshipClaimBase:
    """Common relationship claim fields and endpoint rewiring behavior."""

    source_claim_id: UUID
    target_claim_id: UUID
    metadata: ClaimMetadata
    evidence: ClaimEvidence = field(default_factory=ClaimEvidence)
    claim_id: UUID = field(default_factory=uuid4)

    def rewired(self, *, source_claim_id: UUID, target_claim_id: UUID) -> Self:
        """Return a copy with rewired endpoint IDs."""

        return replace(
            self,
            source_claim_id=source_claim_id,
            target_claim_id=target_claim_id,
        )


@dataclass(slots=True, kw_only=True)
class LinkClaim(_RelationshipClaimBase):
    """Relationship claim for payload-free links."""

    kind: LinkKind


@dataclass(slots=True, kw_only=True)
class AssociationClaim(_RelationshipClaimBase):
    """Relationship claim that carries association payload attributes."""

    kind: AssociationKind
    payload: RelationshipClaimEntity | None = None


type AnyRelationshipClaim = LinkClaim | AssociationClaim


def expect_relationship_entity[TEntity](
    entity: object,
    expected_type: type[TEntity],
    *,
    relationship_claim: AnyRelationshipClaim,
) -> TEntity:
    """Return ``entity`` as ``expected_type`` or raise ``TypeError``."""

    if not isinstance(entity, expected_type):
        msg = (
            f"Relationship {relationship_claim.claim_id} expects {expected_type.__name__}, "
            f"got {type(entity).__name__}"
        )
        raise TypeError(msg)
    return entity


def expect_association_payload[TPayload](
    payload: object,
    expected_type: type[TPayload],
    *,
    relationship_claim: AssociationClaim,
) -> TPayload:
    """Return association payload as ``expected_type`` or raise ``TypeError``."""

    if not isinstance(payload, expected_type):
        msg = (
            f"Relationship {relationship_claim.claim_id} payload expects "
            f"{expected_type.__name__}, got {type(payload).__name__}"
        )
        raise TypeError(msg)
    return payload
