from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from sortipy.domain.model import Artist, Provider, User
from sortipy.domain.reconciliation import ClaimGraph, ClaimMetadata, EntityClaim
from sortipy.domain.reconciliation.apply import apply_resolution_plan
from sortipy.domain.reconciliation.contracts import (
    ApplyInstruction,
    ApplyStrategy,
)

if TYPE_CHECKING:
    from sortipy.domain.reconciliation.contracts import InstructionsByClaim


def test_apply_resolution_plan_counts_instruction_outcomes() -> None:
    create_claim = EntityClaim(
        entity=Artist(name="Create Artist"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    noop_claim = EntityClaim(
        entity=Artist(name="Noop Artist"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    review_claim = EntityClaim(
        entity=Artist(name="Review Artist"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )

    graph = ClaimGraph()
    graph.add(create_claim)
    graph.add(noop_claim)
    graph.add(review_claim)

    instructions: InstructionsByClaim = {
        create_claim.claim_id: ApplyInstruction(strategy=ApplyStrategy.CREATE),
        noop_claim.claim_id: ApplyInstruction(strategy=ApplyStrategy.NOOP),
        review_claim.claim_id: ApplyInstruction(strategy=ApplyStrategy.MANUAL_REVIEW),
    }

    result = apply_resolution_plan(graph, instructions_by_claim=instructions)

    assert result.applied == 3
    assert result.created == 1
    assert result.merged == 0
    assert result.skipped == 1
    assert result.manual_review == 1


def test_apply_resolution_plan_points_merged_claim_to_canonical_target() -> None:
    incoming = Artist(name="Incoming")
    canonical = Artist(name="Canonical")
    claim = EntityClaim(
        entity=incoming,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    graph = ClaimGraph()
    graph.add(claim)

    instructions: InstructionsByClaim = {
        claim.claim_id: ApplyInstruction(
            strategy=ApplyStrategy.MERGE,
            target=canonical,
        )
    }

    result = apply_resolution_plan(graph, instructions_by_claim=instructions)

    assert incoming.canonical_id == canonical.resolved_id
    assert result.applied == 1
    assert result.merged == 1


def test_apply_resolution_plan_rejects_merge_without_target() -> None:
    claim = EntityClaim(
        entity=Artist(name="Incoming"),
        metadata=ClaimMetadata(source=Provider.LASTFM),
    )
    graph = ClaimGraph()
    graph.add(claim)

    instructions: InstructionsByClaim = {
        claim.claim_id: ApplyInstruction(strategy=ApplyStrategy.MERGE)
    }

    with pytest.raises(ValueError, match="missing target"):
        apply_resolution_plan(graph, instructions_by_claim=instructions)


def test_apply_resolution_plan_rejects_merge_for_non_canonicalizable_entities() -> None:
    claim = EntityClaim(
        entity=User(display_name="Listener"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(claim)

    instructions: InstructionsByClaim = {
        claim.claim_id: ApplyInstruction(
            strategy=ApplyStrategy.MERGE,
            target=User(display_name="Canonical Listener"),
        )
    }

    with pytest.raises(TypeError, match="does not support canonical merge"):
        apply_resolution_plan(graph, instructions_by_claim=instructions)


def test_apply_resolution_plan_rejects_unknown_claim_instruction() -> None:
    graph = ClaimGraph()
    instructions: InstructionsByClaim = {
        UUID("00000000-0000-0000-0000-000000000123"): ApplyInstruction(strategy=ApplyStrategy.NOOP)
    }

    with pytest.raises(ValueError, match="unknown claim"):
        apply_resolution_plan(graph, instructions_by_claim=instructions)
