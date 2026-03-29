from __future__ import annotations

from contextlib import nullcontext
from typing import TYPE_CHECKING, Self, cast

from sortipy.application.release_updates import reconcile_release_updates
from sortipy.domain.model import ExternalNamespace, Provider, ReleaseSet
from sortipy.domain.reconciliation import PreparedReconciliation, ResolvedResolution

if TYPE_CHECKING:
    import pytest

    from sortipy.adapters.musicbrainz.candidates import MusicBrainzReleaseCandidate
    from sortipy.domain.model import Release
    from sortipy.domain.reconciliation import ClaimGraph, ReconciliationEngine
    from sortipy.domain.reconciliation.persist import ReconciliationUnitOfWork


class _FakeReleaseRepository:
    def __init__(self, releases: list[Release]) -> None:
        self._releases = releases

    def list(self, *, limit: int | None = None) -> list[Release]:
        if limit is None:
            return list(self._releases)
        return list(self._releases[:limit])


class _FakeRepositories:
    def __init__(self, releases: list[Release]) -> None:
        self.releases = _FakeReleaseRepository(releases)


class _FakeUnitOfWork:
    def __init__(self, releases: list[Release]) -> None:
        self.repositories = _FakeRepositories(releases)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> bool:
        _ = (exc_type, exc_value, traceback)
        return False

    def commit(self) -> None:
        raise AssertionError("anchor mismatches must not commit")

    def rollback(self) -> None:
        return None

    def suspend_autoflush(self) -> object:
        return nullcontext()


class _AnchorMismatchEngine:
    def __init__(self, resolved_target: Release) -> None:
        self._resolved_target = resolved_target

    def prepare(self, graph: ClaimGraph, *, repositories: object) -> PreparedReconciliation:
        _ = repositories
        root_claim = graph.roots[0]
        return PreparedReconciliation(
            graph=graph,
            keys_by_claim={},
            deduplicated_graph=graph,
            representatives_by_claim={},
            entity_resolutions_by_claim={
                root_claim.claim_id: ResolvedResolution(target=self._resolved_target)
            },
            association_resolutions_by_claim={},
            link_resolutions_by_claim={},
        )

    def execute(self, prepared: object, *, uow: object) -> object:
        _ = (prepared, uow)
        raise AssertionError("anchor mismatches must stop before execute")


def test_reconcile_release_updates_logs_anchor_mismatch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    target_release_set = ReleaseSet(title="BLUSH")
    target_release = target_release_set.create_release(title="BLUSH")
    target_release.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RELEASE,
        "e6b9c875-f521-4261-892b-b0318a1b9b1b",
    )

    resolved_release_set = ReleaseSet(title="Different Release")
    resolved_release = resolved_release_set.create_release(title="Different Release")

    fetched_release_set = ReleaseSet(title="BLUSH")
    fetched_release = fetched_release_set.create_release(title="BLUSH")
    fetched_release.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RELEASE,
        "0772539c-7916-4504-bfdd-3ea8e011bb4d",
        provider=Provider.MUSICBRAINZ,
    )

    def fake_fetch_release_graph(candidate: MusicBrainzReleaseCandidate) -> Release:
        _ = candidate
        return fetched_release

    def fake_fetch_candidates_from_recording(
        recording: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = recording
        return []

    def fake_fetch_candidates_from_release_set(
        release_set: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = release_set
        return []

    def fake_fetch_candidates_from_artist(artist: object) -> list[MusicBrainzReleaseCandidate]:
        _ = artist
        return []

    def fake_uow_factory() -> ReconciliationUnitOfWork:
        return cast("ReconciliationUnitOfWork", _FakeUnitOfWork([target_release]))

    caplog.set_level("INFO")
    result = reconcile_release_updates(
        fetch_release_graph=fake_fetch_release_graph,
        fetch_candidates_from_recording=fake_fetch_candidates_from_recording,
        fetch_candidates_from_release_set=fake_fetch_candidates_from_release_set,
        fetch_candidates_from_artist=fake_fetch_candidates_from_artist,
        unit_of_work_factory=fake_uow_factory,
        source=Provider.MUSICBRAINZ,
        engine=cast("ReconciliationEngine", _AnchorMismatchEngine(resolved_release)),
    )

    assert result.anchor_mismatches == 1
    assert result.fetched_updates == 1
    assert result.applied_releases == 0
    assert "MusicBrainz anchor mismatch for release BLUSH" in caplog.text
    assert "requested_mbid=e6b9c875-f521-4261-892b-b0318a1b9b1b" in caplog.text
    assert "fetched_mbid=0772539c-7916-4504-bfdd-3ea8e011bb4d" in caplog.text
    assert "candidate_entity_ids=" in caplog.text
