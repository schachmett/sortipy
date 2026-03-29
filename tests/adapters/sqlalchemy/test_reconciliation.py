from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.exc import SAWarning

from sortipy.domain.model import (
    Artist,
    ArtistRole,
    EntityType,
    PartialDate,
    Provider,
    Release,
    ReleaseSet,
    ReleaseSetContribution,
    ReleaseSetSecondaryType,
)
from sortipy.domain.reconciliation import (
    AssociationClaim,
    AssociationKind,
    ClaimGraph,
    ClaimMetadata,
    CreateInstruction,
    EntityClaim,
    NoopInstruction,
)
from sortipy.domain.reconciliation.apply import ApplyResult
from sortipy.domain.reconciliation.persist import persist_reconciliation

if TYPE_CHECKING:
    from collections.abc import Callable

    from sortipy.adapters.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork
    from sortipy.domain.reconciliation.contracts import (
        AssociationInstructionsByClaim,
        EntityInstructionsByClaim,
        KeysByClaim,
        LinkInstructionsByClaim,
    )


@dataclass(slots=True)
class _PriorityKeysData:
    priority_keys: tuple[tuple[object, ...], ...]


def test_persist_reconciliation_commits_created_entities_and_sidecars(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    artist_claim = EntityClaim(
        entity=Artist(name="Massive Attack"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(artist_claim)

    keys_by_claim: KeysByClaim = {
        artist_claim.claim_id: (("artist:name", "massive attack"),),
    }
    entity_instructions_by_claim: EntityInstructionsByClaim = {
        artist_claim.claim_id: CreateInstruction(),
    }
    association_instructions_by_claim: AssociationInstructionsByClaim = {}
    link_instructions_by_claim: LinkInstructionsByClaim = {}

    with sqlite_unit_of_work() as uow:
        result = persist_reconciliation(
            graph=graph,
            keys_by_claim=keys_by_claim,
            entity_instructions_by_claim=entity_instructions_by_claim,
            association_instructions_by_claim=association_instructions_by_claim,
            link_instructions_by_claim=link_instructions_by_claim,
            apply_result=_empty_apply_result(),
            uow=uow,
        )

    assert result.committed is True
    assert result.persisted_entities == 1
    assert result.persisted_sidecars == 1

    with sqlite_unit_of_work() as uow:
        matches = uow.repositories.normalization_sidecars.find_by_keys(
            EntityType.ARTIST,
            (("artist:name", "massive attack"),),
        )

    matched = matches.get(("artist:name", "massive attack"))
    assert isinstance(matched, Artist)
    assert matched.name == "Massive Attack"


def test_persist_reconciliation_counts_only_new_sidecars(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    existing = Artist(name="Massive Attack")

    with sqlite_unit_of_work() as uow:
        uow.repositories.artists.add(existing)
        uow.repositories.normalization_sidecars.save(
            existing,
            _priority_keys_data((("artist:name", "massive attack"),)),
        )
        uow.commit()

    incoming_claim = EntityClaim(
        entity=Artist(name="MASSIVE ATTACK"),
        metadata=ClaimMetadata(source=Provider.SPOTIFY),
    )
    graph = ClaimGraph()
    graph.add(incoming_claim)

    keys_by_claim: KeysByClaim = {
        incoming_claim.claim_id: (("artist:name", "massive attack"),),
    }
    entity_instructions_by_claim: EntityInstructionsByClaim = {
        incoming_claim.claim_id: NoopInstruction(target=existing),
    }
    association_instructions_by_claim: AssociationInstructionsByClaim = {}
    link_instructions_by_claim: LinkInstructionsByClaim = {}

    with sqlite_unit_of_work() as uow:
        result = persist_reconciliation(
            graph=graph,
            keys_by_claim=keys_by_claim,
            entity_instructions_by_claim=entity_instructions_by_claim,
            association_instructions_by_claim=association_instructions_by_claim,
            link_instructions_by_claim=link_instructions_by_claim,
            apply_result=_empty_apply_result(),
            uow=uow,
        )

    assert result.committed is True
    assert result.persisted_entities == 0
    assert result.persisted_sidecars == 0


def test_mutation_repository_persists_existing_entity_list_and_provenance_updates(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    release_set = ReleaseSet(title="Mezzanine")

    with sqlite_unit_of_work() as uow:
        uow.repositories.release_sets.add(release_set)
        uow.commit()

    with sqlite_unit_of_work() as uow:
        loaded = uow.session.get(ReleaseSet, release_set.id)
        assert loaded is not None
        loaded.secondary_types.append(ReleaseSetSecondaryType.COMPILATION)
        loaded.mark_changed("secondary_types")
        loaded.add_source(Provider.MUSICBRAINZ)
        uow.repositories.mutations.update(loaded, changed_fields=loaded.changed_fields)
        uow.commit()

    with sqlite_unit_of_work() as uow:
        loaded = uow.session.get(ReleaseSet, release_set.id)
        assert loaded is not None
        assert loaded.secondary_types == [ReleaseSetSecondaryType.COMPILATION]
        assert loaded.provenance is not None
        assert loaded.provenance.sources == {Provider.MUSICBRAINZ}


def test_mutation_repository_persists_existing_association_field_updates(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    artist = Artist(name="Massive Attack")
    release_set = ReleaseSet(title="Mezzanine")
    release_set.add_artist(artist, role=ArtistRole.PRIMARY)

    with sqlite_unit_of_work() as uow:
        uow.repositories.artists.add(artist)
        uow.repositories.release_sets.add(release_set)
        uow.commit()

    with sqlite_unit_of_work() as uow:
        loaded_release_set = uow.session.get(ReleaseSet, release_set.id)
        assert loaded_release_set is not None
        loaded_contribution = loaded_release_set.contributions[0]
        loaded_contribution.join_phrase = " feat. "
        loaded_contribution.mark_changed("join_phrase")
        uow.repositories.mutations.update(
            loaded_contribution,
            changed_fields=loaded_contribution.changed_fields,
        )
        uow.commit()

    with sqlite_unit_of_work() as uow:
        loaded_release_set = uow.session.get(ReleaseSet, release_set.id)
        assert loaded_release_set is not None
        assert loaded_release_set.contributions[0].join_phrase == " feat. "


def test_mutation_repository_does_not_flag_modified_for_composite_updates(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    release_set = ReleaseSet(title="Mezzanine")
    release = release_set.create_release(title="Mezzanine")

    with sqlite_unit_of_work() as uow:
        uow.repositories.release_sets.add(release_set)
        uow.repositories.releases.add(release)
        uow.commit()

    with sqlite_unit_of_work() as uow:
        loaded_release_set = uow.session.get(ReleaseSet, release_set.id)
        loaded_release = uow.session.get(Release, release.id)
        assert loaded_release_set is not None
        assert loaded_release is not None

        loaded_release_set.first_release = PartialDate(year=1998, month=4, day=20)
        loaded_release_set.mark_changed("first_release")
        loaded_release.release_date = PartialDate(year=1998, month=4, day=20)
        loaded_release.mark_changed("release_date")

        uow.repositories.mutations.update(
            loaded_release_set,
            changed_fields=loaded_release_set.changed_fields,
        )
        uow.repositories.mutations.update(
            loaded_release,
            changed_fields=loaded_release.changed_fields,
        )
        uow.commit()

    with sqlite_unit_of_work() as uow:
        loaded_release_set = uow.session.get(ReleaseSet, release_set.id)
        loaded_release = uow.session.get(Release, release.id)
        assert loaded_release_set is not None
        assert loaded_release is not None
        assert loaded_release_set.first_release == PartialDate(year=1998, month=4, day=20)
        assert loaded_release.release_date == PartialDate(year=1998, month=4, day=20)


def test_persist_reconciliation_attaches_created_release_set_contributions(
    sqlite_unit_of_work: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    persistent_artist = Artist(name="Massive Attack")
    persistent_release_set = ReleaseSet(title="Mezzanine")

    with sqlite_unit_of_work() as uow:
        uow.repositories.artists.add(persistent_artist)
        uow.repositories.release_sets.add(persistent_release_set)
        uow.commit()

    transient_artist = Artist(name="Incoming Artist")
    transient_release_set = ReleaseSet(title="Incoming Release Set")
    transient_contribution = transient_release_set.add_artist(
        transient_artist,
        role=ArtistRole.PRIMARY,
    )

    graph = ClaimGraph()
    apply_result = ApplyResult()

    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        with sqlite_unit_of_work() as uow:
            loaded_artist = uow.session.get(Artist, persistent_artist.id)
            loaded_release_set = uow.session.get(ReleaseSet, persistent_release_set.id)
            assert loaded_artist is not None
            assert loaded_release_set is not None

            adopted = loaded_release_set.adopt_contribution(
                transient_contribution,
                artist=loaded_artist,
            )
            assert isinstance(adopted, ReleaseSetContribution)

            release_set_claim = EntityClaim(
                entity=loaded_release_set,
                metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
            )
            artist_claim = EntityClaim(
                entity=loaded_artist,
                metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
            )
            association_claim = AssociationClaim(
                source_claim_id=release_set_claim.claim_id,
                target_claim_id=artist_claim.claim_id,
                kind=AssociationKind.RELEASE_SET_CONTRIBUTION,
                metadata=ClaimMetadata(source=Provider.MUSICBRAINZ),
                payload=adopted,
            )
            graph.add(release_set_claim)
            graph.add(artist_claim)
            graph.add_relationship(association_claim)
            apply_result.associations_by_claim[association_claim.claim_id] = adopted

            persist_reconciliation(
                graph=graph,
                keys_by_claim={},
                entity_instructions_by_claim={},
                association_instructions_by_claim={
                    association_claim.claim_id: CreateInstruction(),
                },
                link_instructions_by_claim={},
                apply_result=apply_result,
                uow=uow,
            )

    with sqlite_unit_of_work() as uow:
        count = uow.session.execute(
            text("select count(*) from release_set_contribution"),
        ).scalar_one()
        loaded_release_set = uow.session.get(ReleaseSet, persistent_release_set.id)
        assert loaded_release_set is not None
        assert count == 1
        assert len(loaded_release_set.contributions) == 1


def _empty_apply_result() -> ApplyResult:
    return ApplyResult()


def _priority_keys_data(priority_keys: tuple[tuple[object, ...], ...]) -> _PriorityKeysData:
    return _PriorityKeysData(priority_keys=priority_keys)
