from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from sortipy.domain.model import (
    Artist,
    ArtistRole,
    Label,
    Provider,
    Recording,
    RecordingContribution,
    ReleaseSet,
    ReleaseTrack,
    User,
)
from sortipy.domain.reconciliation import (
    AssociationClaim,
    AssociationKind,
    ClaimGraph,
    ClaimMetadata,
    EntityClaim,
    LinkClaim,
    LinkKind,
)
from sortipy.domain.reconciliation.apply import apply_reconciliation_instructions
from sortipy.domain.reconciliation.contracts import (
    CreateInstruction,
    LinkCreateInstruction,
    LinkManualReviewInstruction,
    LinkNoopInstruction,
    ManualReviewInstruction,
    ManualReviewSubject,
    MergeInstruction,
    NoopInstruction,
)

if TYPE_CHECKING:
    from sortipy.domain.reconciliation.contracts import (
        AssociationInstructionsByClaim,
        EntityInstructionsByClaim,
        LinkInstructionsByClaim,
    )


def test_apply_reconciliation_instructions_counts_instruction_outcomes() -> None:
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

    entity_instructions: EntityInstructionsByClaim = {
        create_claim.claim_id: CreateInstruction(),
        noop_claim.claim_id: NoopInstruction(),
        review_claim.claim_id: ManualReviewInstruction(),
    }

    result = apply_reconciliation_instructions(
        graph,
        entity_instructions_by_claim=entity_instructions,
        association_instructions_by_claim={},
        link_instructions_by_claim={},
    )

    assert result.entities.applied == 3
    assert result.entities.merged == 0
    assert result.entities.created == 1
    assert result.entities.skipped == 1
    assert result.entities.manual_review == 1
    assert len(result.manual_review_items) == 1
    assert result.manual_review_items[0].subject is ManualReviewSubject.ENTITY


def test_apply_reconciliation_instructions_merges_entity_fields_into_target() -> None:
    incoming = Artist(name="Incoming")
    canonical = Artist(name="Canonical")
    claim = EntityClaim(
        entity=incoming,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    graph = ClaimGraph()
    graph.add(claim)

    entity_instructions: EntityInstructionsByClaim = {
        claim.claim_id: MergeInstruction(target=canonical)
    }

    result = apply_reconciliation_instructions(
        graph,
        entity_instructions_by_claim=entity_instructions,
        association_instructions_by_claim={},
        link_instructions_by_claim={},
    )

    assert canonical.name == "Incoming"
    assert result.entities.applied == 1
    assert result.entities.merged == 1


def test_apply_reconciliation_instructions_rejects_merge_without_target() -> None:
    claim = EntityClaim(
        entity=Artist(name="Incoming"),
        metadata=ClaimMetadata(source=Provider.LASTFM),
    )
    graph = ClaimGraph()
    graph.add(claim)

    with pytest.raises(TypeError, match="missing 1 required keyword-only argument"):
        _ = MergeInstruction()  # type: ignore[call-arg]


def test_apply_reconciliation_instructions_merges_user_fields_into_target() -> None:
    claim = EntityClaim(
        entity=User(display_name="Listener", email="listener@example.com"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(claim)

    canonical = User(display_name="Old", email=None)
    entity_instructions: EntityInstructionsByClaim = {
        claim.claim_id: MergeInstruction(target=canonical)
    }

    result = apply_reconciliation_instructions(
        graph,
        entity_instructions_by_claim=entity_instructions,
        association_instructions_by_claim={},
        link_instructions_by_claim={},
    )
    assert canonical.display_name == "Listener"
    assert canonical.email == "listener@example.com"
    assert result.entities.merged == 1


def test_apply_reconciliation_instructions_rejects_unknown_claim_instruction() -> None:
    graph = ClaimGraph()
    entity_instructions: EntityInstructionsByClaim = {
        UUID("00000000-0000-0000-0000-000000000123"): NoopInstruction()
    }

    with pytest.raises(ValueError, match="Unknown claim"):
        apply_reconciliation_instructions(
            graph,
            entity_instructions_by_claim=entity_instructions,
            association_instructions_by_claim={},
            link_instructions_by_claim={},
        )


def test_apply_reconciliation_instructions_creates_release_label_link() -> None:
    release_set = ReleaseSet(title="Kid A")
    release = release_set.create_release(title="Kid A")
    label = Label(name="Parlophone")
    release_claim = EntityClaim(entity=release, metadata=ClaimMetadata(source=Provider.SPOTIFY))
    label_claim = EntityClaim(entity=label, metadata=ClaimMetadata(source=Provider.SPOTIFY))
    link_claim = LinkClaim(
        source_claim_id=release_claim.claim_id,
        target_claim_id=label_claim.claim_id,
        kind=LinkKind.RELEASE_LABEL,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )

    graph = ClaimGraph()
    graph.add(release_claim)
    graph.add(label_claim)
    graph.add_relationship(link_claim)

    entity_instructions: EntityInstructionsByClaim = {
        release_claim.claim_id: CreateInstruction(),
        label_claim.claim_id: CreateInstruction(),
    }
    link_instructions: LinkInstructionsByClaim = {link_claim.claim_id: LinkCreateInstruction()}

    result = apply_reconciliation_instructions(
        graph,
        entity_instructions_by_claim=entity_instructions,
        association_instructions_by_claim={},
        link_instructions_by_claim=link_instructions,
    )

    assert label in release.labels
    assert result.links.applied == 1
    assert result.links.created == 1


def test_apply_reconciliation_instructions_counts_link_noop_and_manual_review() -> None:
    release_set = ReleaseSet(title="Source")
    source_release = release_set.create_release(title="Source")
    label = Label(name="Target")

    source_claim = EntityClaim(
        entity=source_release,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    target_claim = EntityClaim(
        entity=label,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    noop_link = LinkClaim(
        source_claim_id=source_claim.claim_id,
        target_claim_id=target_claim.claim_id,
        kind=LinkKind.RELEASE_LABEL,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    review_link = LinkClaim(
        source_claim_id=source_claim.claim_id,
        target_claim_id=target_claim.claim_id,
        kind=LinkKind.RELEASE_LABEL,
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )

    graph = ClaimGraph()
    graph.add(source_claim)
    graph.add(target_claim)
    graph.add_relationship(noop_link)
    graph.add_relationship(review_link)

    link_instructions: LinkInstructionsByClaim = {
        noop_link.claim_id: LinkNoopInstruction(),
        review_link.claim_id: LinkManualReviewInstruction(),
    }

    result = apply_reconciliation_instructions(
        graph,
        entity_instructions_by_claim={},
        association_instructions_by_claim={},
        link_instructions_by_claim=link_instructions,
    )

    assert result.links.applied == 2
    assert result.links.skipped == 1
    assert result.links.manual_review == 1
    assert len(result.manual_review_items) == 1
    assert result.manual_review_items[0].subject is ManualReviewSubject.LINK


def test_apply_reconciliation_instructions_merges_association_payload() -> None:
    release_set = ReleaseSet(title="Kid A")
    release = release_set.create_release(title="Kid A")
    recording = Recording(title="Everything in Its Right Place")
    existing_track = release.add_track(
        recording,
        disc_number=1,
        track_number=1,
    )
    incoming_release = release_set.create_release(title="Incoming")
    incoming_recording = Recording(title="Incoming Recording")
    incoming_payload = incoming_release.add_track(
        incoming_recording,
        disc_number=2,
        track_number=7,
        title_override="Incoming Title",
    )

    release_claim = EntityClaim(
        entity=release,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    recording_claim = EntityClaim(
        entity=recording,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    association_claim = AssociationClaim(
        source_claim_id=release_claim.claim_id,
        target_claim_id=recording_claim.claim_id,
        kind=AssociationKind.RELEASE_TRACK,
        payload=incoming_payload,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )

    graph = ClaimGraph()
    graph.add(release_claim)
    graph.add(recording_claim)
    graph.add_relationship(association_claim)

    association_instructions: AssociationInstructionsByClaim = {
        association_claim.claim_id: MergeInstruction(target=existing_track)
    }

    result = apply_reconciliation_instructions(
        graph,
        entity_instructions_by_claim={},
        association_instructions_by_claim=association_instructions,
        link_instructions_by_claim={},
    )

    assert existing_track.disc_number == 2
    assert existing_track.track_number == 7
    assert existing_track.title_override == "Incoming Title"
    assert result.associations.applied == 1
    assert result.associations.merged == 1


def test_apply_reconciliation_instructions_exposes_materialized_objects_by_claim() -> None:
    release_set = ReleaseSet(title="Kid A")
    release = release_set.create_release(title="Kid A")
    recording = Recording(title="Everything in Its Right Place")
    artist = Artist(name="Radiohead")
    incoming_track = release.add_track(recording, track_number=1)
    incoming_contribution = recording.add_artist(artist, role=ArtistRole.PRIMARY)

    release_claim = EntityClaim(
        entity=release,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    recording_claim = EntityClaim(
        entity=recording,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    artist_claim = EntityClaim(
        entity=artist,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    track_claim = AssociationClaim(
        source_claim_id=release_claim.claim_id,
        target_claim_id=recording_claim.claim_id,
        kind=AssociationKind.RELEASE_TRACK,
        payload=incoming_track,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )
    contribution_claim = AssociationClaim(
        source_claim_id=recording_claim.claim_id,
        target_claim_id=artist_claim.claim_id,
        kind=AssociationKind.RECORDING_CONTRIBUTION,
        payload=incoming_contribution,
        metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
    )

    graph = ClaimGraph()
    graph.add(release_claim)
    graph.add(recording_claim)
    graph.add(artist_claim)
    graph.add_relationship(track_claim)
    graph.add_relationship(contribution_claim)

    result = apply_reconciliation_instructions(
        graph,
        entity_instructions_by_claim={
            release_claim.claim_id: CreateInstruction(),
            recording_claim.claim_id: CreateInstruction(),
            artist_claim.claim_id: CreateInstruction(),
        },
        association_instructions_by_claim={
            track_claim.claim_id: CreateInstruction(),
            contribution_claim.claim_id: CreateInstruction(),
        },
        link_instructions_by_claim={},
    )

    assert result.entities_by_claim[release_claim.claim_id] is release
    assert result.entities_by_claim[recording_claim.claim_id] is recording
    materialized_track = result.associations_by_claim[track_claim.claim_id]
    materialized_contribution = result.associations_by_claim[contribution_claim.claim_id]
    assert isinstance(materialized_track, ReleaseTrack)
    assert isinstance(materialized_contribution, RecordingContribution)
    assert materialized_track.recording is recording
    assert materialized_contribution.artist is artist
