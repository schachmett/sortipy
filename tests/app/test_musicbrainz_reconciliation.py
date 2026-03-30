from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING, Self, cast

from sortipy.adapters.musicbrainz.candidates import MusicBrainzReleaseGraphFetchResult
from sortipy.adapters.musicbrainz.client import MusicBrainzAPIError
from sortipy.application.release_updates import reconcile_release_updates
from sortipy.domain.model import ExternalNamespace, Provider, ReleaseSet
from sortipy.domain.reconciliation import (
    ApplyCounters,
    ApplyResult,
    PreparedReconciliation,
    ResolvedResolution,
)

if TYPE_CHECKING:
    import pytest

    from sortipy.adapters.musicbrainz.candidates import (
        MusicBrainzReleaseCandidate,
    )
    from sortipy.domain.model import Namespace, Release
    from sortipy.domain.reconciliation import ClaimGraph, ReconciliationEngine
    from sortipy.domain.reconciliation.persist import ReconciliationUnitOfWork


@dataclass(slots=True)
class _SavedRedirect:
    namespace: object
    source_value: str
    target_value: str
    provider: Provider | None


class _FakeExternalIdRedirectRepository:
    def __init__(self) -> None:
        self.saved: list[_SavedRedirect] = []

    def save_redirect(
        self,
        namespace: Namespace,
        source_value: str,
        target_value: str,
        *,
        provider: Provider | None = None,
    ) -> None:
        self.saved.append(
            _SavedRedirect(
                namespace=namespace,
                source_value=source_value,
                target_value=target_value,
                provider=provider,
            )
        )

    def resolve(self, namespace: Namespace, value: str) -> None:
        _ = (namespace, value)


class _FakeReleaseRepository:
    def __init__(self, releases: list[Release]) -> None:
        self._releases = releases

    def list(self, *, limit: int | None = None) -> list[Release]:
        if limit is None:
            return list(self._releases)
        return list(self._releases[:limit])

    def get_by_external_id(self, namespace: Namespace, value: str) -> Release | None:
        for release in self._releases:
            entry = release.external_ids_by_namespace.get(namespace)
            if entry is not None and entry.value == value:
                return release
        return None


class _FakeReleaseSetRepository:
    def __init__(self, release_sets: list[ReleaseSet]) -> None:
        self._release_sets = release_sets

    def get_by_external_id(self, namespace: Namespace, value: str) -> ReleaseSet | None:
        for release_set in self._release_sets:
            entry = release_set.external_ids_by_namespace.get(namespace)
            if entry is not None and entry.value == value:
                return release_set
        return None


class _FakeRepositories:
    def __init__(self, releases: list[Release]) -> None:
        self.releases = _FakeReleaseRepository(releases)
        self.release_sets = _FakeReleaseSetRepository([release.release_set for release in releases])
        self.external_id_redirects = _FakeExternalIdRedirectRepository()


class _FakeUnitOfWork:
    def __init__(self, releases: list[Release]) -> None:
        self.repositories = _FakeRepositories(releases)
        self.commit_calls = 0

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
        self.commit_calls += 1

    def rollback(self) -> None:
        return None

    def suspend_autoflush(self) -> object:
        return nullcontext()


class _PreparedEngine:
    def __init__(self, resolved_target: Release) -> None:
        self._resolved_target = resolved_target
        self.execute_calls = 0

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
        self.execute_calls += 1
        return SimpleNamespace(
            apply_result=ApplyResult(
                entities=ApplyCounters(),
                associations=ApplyCounters(),
                links=ApplyCounters(),
                manual_review_items=[],
            ),
            persistence_result=SimpleNamespace(
                persisted_entities=0,
                persisted_sidecars=0,
            ),
        )


def test_reconcile_release_updates_logs_anchor_mismatch_and_restores_redirect_state(
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

    def fake_fetch_release_graph(
        candidate: MusicBrainzReleaseCandidate,
    ) -> MusicBrainzReleaseGraphFetchResult:
        return MusicBrainzReleaseGraphFetchResult(
            release=fetched_release,
            requested_mbid=candidate.mbid,
            resolved_mbid="0772539c-7916-4504-bfdd-3ea8e011bb4d",
            redirected=True,
        )

    def fake_fetch_candidates_from_recording(
        recording: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = recording
        return []

    def fake_fetch_candidates_from_release(
        release: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = release
        return []

    def fake_fetch_candidates_from_release_set(
        release_set: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = release_set
        return []

    def fake_fetch_candidates_from_artist(artist: object) -> list[MusicBrainzReleaseCandidate]:
        _ = artist
        return []

    fake_uow = _FakeUnitOfWork([target_release])

    def fake_uow_factory() -> ReconciliationUnitOfWork:
        return cast("ReconciliationUnitOfWork", fake_uow)

    caplog.set_level("INFO")
    result = reconcile_release_updates(
        fetch_release_graph=fake_fetch_release_graph,
        fetch_candidates_from_recording=fake_fetch_candidates_from_recording,
        fetch_candidates_from_release=fake_fetch_candidates_from_release,
        fetch_candidates_from_release_set=fake_fetch_candidates_from_release_set,
        fetch_candidates_from_artist=fake_fetch_candidates_from_artist,
        unit_of_work_factory=fake_uow_factory,
        source=Provider.MUSICBRAINZ,
        engine=cast("ReconciliationEngine", _PreparedEngine(resolved_release)),
    )

    assert result.anchor_mismatches == 1
    assert result.fetched_updates == 1
    assert result.applied_releases == 0
    assert (
        target_release.external_ids_by_namespace[ExternalNamespace.MUSICBRAINZ_RELEASE].value
        == "e6b9c875-f521-4261-892b-b0318a1b9b1b"
    )
    assert fake_uow.repositories.external_id_redirects.saved == []
    assert "MusicBrainz anchor mismatch for release BLUSH" in caplog.text
    assert "requested_mbid=e6b9c875-f521-4261-892b-b0318a1b9b1b" in caplog.text
    assert "fetched_mbid=0772539c-7916-4504-bfdd-3ea8e011bb4d" in caplog.text
    assert "candidate_entity_ids=" in caplog.text


def test_reconcile_release_updates_saves_redirect_and_applies_release_update() -> None:
    target_release_set = ReleaseSet(title="BLUSH")
    target_release = target_release_set.create_release(title="BLUSH")
    target_release.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RELEASE,
        "e6b9c875-f521-4261-892b-b0318a1b9b1b",
    )

    fetched_release_set = ReleaseSet(title="BLUSH")
    fetched_release = fetched_release_set.create_release(title="BLUSH")
    fetched_release.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RELEASE,
        "0772539c-7916-4504-bfdd-3ea8e011bb4d",
        provider=Provider.MUSICBRAINZ,
    )

    def fake_fetch_release_graph(
        candidate: MusicBrainzReleaseCandidate,
    ) -> MusicBrainzReleaseGraphFetchResult:
        return MusicBrainzReleaseGraphFetchResult(
            release=fetched_release,
            requested_mbid=candidate.mbid,
            resolved_mbid="0772539c-7916-4504-bfdd-3ea8e011bb4d",
            redirected=True,
        )

    def fake_fetch_candidates_from_recording(
        recording: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = recording
        return []

    def fake_fetch_candidates_from_release(
        release: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = release
        return []

    def fake_fetch_candidates_from_release_set(
        release_set: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = release_set
        return []

    def fake_fetch_candidates_from_artist(artist: object) -> list[MusicBrainzReleaseCandidate]:
        _ = artist
        return []

    fake_uow = _FakeUnitOfWork([target_release])
    fake_engine = _PreparedEngine(target_release)

    def fake_uow_factory() -> ReconciliationUnitOfWork:
        return cast("ReconciliationUnitOfWork", fake_uow)

    result = reconcile_release_updates(
        fetch_release_graph=fake_fetch_release_graph,
        fetch_candidates_from_recording=fake_fetch_candidates_from_recording,
        fetch_candidates_from_release=fake_fetch_candidates_from_release,
        fetch_candidates_from_release_set=fake_fetch_candidates_from_release_set,
        fetch_candidates_from_artist=fake_fetch_candidates_from_artist,
        unit_of_work_factory=fake_uow_factory,
        limit=1,
        source=Provider.MUSICBRAINZ,
        engine=cast("ReconciliationEngine", fake_engine),
    )

    assert result.anchor_mismatches == 0
    assert result.applied_releases == 1
    assert fake_engine.execute_calls == 1
    assert (
        target_release.external_ids_by_namespace[ExternalNamespace.MUSICBRAINZ_RELEASE].value
        == "0772539c-7916-4504-bfdd-3ea8e011bb4d"
    )
    assert fake_uow.repositories.external_id_redirects.saved == [
        _SavedRedirect(
            namespace=ExternalNamespace.MUSICBRAINZ_RELEASE,
            source_value="e6b9c875-f521-4261-892b-b0318a1b9b1b",
            target_value="0772539c-7916-4504-bfdd-3ea8e011bb4d",
            provider=Provider.MUSICBRAINZ,
        )
    ]


def test_reconcile_release_updates_applies_missing_candidate_anchor() -> None:
    target_release_set = ReleaseSet(title="Somersaults")
    target_release = target_release_set.create_release(title="Somersaults")

    fetched_release_set = ReleaseSet(title="Somersaults")
    fetched_release_set.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP,
        "95f25301-da18-4fe9-9445-8dc453adfe78",
        provider=Provider.MUSICBRAINZ,
    )
    fetched_release = fetched_release_set.create_release(title="Somersaults")
    fetched_release.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RELEASE,
        "6ab3e4d6-0bc3-4162-93db-f1bbee2c0e38",
        provider=Provider.MUSICBRAINZ,
    )

    def fake_fetch_release_graph(
        candidate: MusicBrainzReleaseCandidate,
    ) -> MusicBrainzReleaseGraphFetchResult:
        return MusicBrainzReleaseGraphFetchResult(
            release=fetched_release,
            requested_mbid=candidate.mbid,
            resolved_mbid="6ab3e4d6-0bc3-4162-93db-f1bbee2c0e38",
            redirected=False,
        )

    def fake_fetch_candidates_from_recording(
        recording: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = recording
        return []

    def fake_fetch_candidates_from_release(
        release: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = release
        return [
            cast(
                "MusicBrainzReleaseCandidate",
                SimpleNamespace(mbid="6ab3e4d6-0bc3-4162-93db-f1bbee2c0e38"),
            )
        ]

    def fake_fetch_candidates_from_release_set(
        release_set: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = release_set
        return []

    def fake_fetch_candidates_from_artist(artist: object) -> list[MusicBrainzReleaseCandidate]:
        _ = artist
        return []

    fake_uow = _FakeUnitOfWork([target_release])
    fake_engine = _PreparedEngine(target_release)

    def fake_uow_factory() -> ReconciliationUnitOfWork:
        return cast("ReconciliationUnitOfWork", fake_uow)

    result = reconcile_release_updates(
        fetch_release_graph=fake_fetch_release_graph,
        fetch_candidates_from_recording=fake_fetch_candidates_from_recording,
        fetch_candidates_from_release=fake_fetch_candidates_from_release,
        fetch_candidates_from_release_set=fake_fetch_candidates_from_release_set,
        fetch_candidates_from_artist=fake_fetch_candidates_from_artist,
        unit_of_work_factory=fake_uow_factory,
        limit=1,
        source=Provider.MUSICBRAINZ,
        engine=cast("ReconciliationEngine", fake_engine),
    )

    assert result.anchor_mismatches == 0
    assert result.applied_releases == 1
    assert fake_engine.execute_calls == 1
    assert (
        target_release.external_ids_by_namespace[ExternalNamespace.MUSICBRAINZ_RELEASE].value
        == "6ab3e4d6-0bc3-4162-93db-f1bbee2c0e38"
    )
    assert (
        target_release.release_set.external_ids_by_namespace[
            ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP
        ].value
        == "95f25301-da18-4fe9-9445-8dc453adfe78"
    )


def test_reconcile_release_updates_restores_missing_candidate_anchor_on_mismatch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    target_release_set = ReleaseSet(title="Somersaults")
    target_release = target_release_set.create_release(title="Somersaults")

    resolved_release_set = ReleaseSet(title="Different Release")
    resolved_release = resolved_release_set.create_release(title="Different Release")

    fetched_release_set = ReleaseSet(title="Somersaults")
    fetched_release_set.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP,
        "95f25301-da18-4fe9-9445-8dc453adfe78",
        provider=Provider.MUSICBRAINZ,
    )
    fetched_release = fetched_release_set.create_release(title="Somersaults")
    fetched_release.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RELEASE,
        "6ab3e4d6-0bc3-4162-93db-f1bbee2c0e38",
        provider=Provider.MUSICBRAINZ,
    )

    def fake_fetch_release_graph(
        candidate: MusicBrainzReleaseCandidate,
    ) -> MusicBrainzReleaseGraphFetchResult:
        return MusicBrainzReleaseGraphFetchResult(
            release=fetched_release,
            requested_mbid=candidate.mbid,
            resolved_mbid="6ab3e4d6-0bc3-4162-93db-f1bbee2c0e38",
            redirected=False,
        )

    def fake_fetch_candidates_from_recording(
        recording: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = recording
        return []

    def fake_fetch_candidates_from_release(
        release: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = release
        return [
            cast(
                "MusicBrainzReleaseCandidate",
                SimpleNamespace(mbid="6ab3e4d6-0bc3-4162-93db-f1bbee2c0e38"),
            )
        ]

    def fake_fetch_candidates_from_release_set(
        release_set: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = release_set
        return []

    def fake_fetch_candidates_from_artist(artist: object) -> list[MusicBrainzReleaseCandidate]:
        _ = artist
        return []

    fake_uow = _FakeUnitOfWork([target_release])

    def fake_uow_factory() -> ReconciliationUnitOfWork:
        return cast("ReconciliationUnitOfWork", fake_uow)

    caplog.set_level("INFO")
    result = reconcile_release_updates(
        fetch_release_graph=fake_fetch_release_graph,
        fetch_candidates_from_recording=fake_fetch_candidates_from_recording,
        fetch_candidates_from_release=fake_fetch_candidates_from_release,
        fetch_candidates_from_release_set=fake_fetch_candidates_from_release_set,
        fetch_candidates_from_artist=fake_fetch_candidates_from_artist,
        unit_of_work_factory=fake_uow_factory,
        source=Provider.MUSICBRAINZ,
        engine=cast("ReconciliationEngine", _PreparedEngine(resolved_release)),
    )

    assert result.anchor_mismatches == 1
    assert result.applied_releases == 0
    assert ExternalNamespace.MUSICBRAINZ_RELEASE not in target_release.external_ids_by_namespace
    assert (
        ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP
        not in target_release.release_set.external_ids_by_namespace
    )
    assert "MusicBrainz anchor mismatch for release Somersaults" in caplog.text


def test_reconcile_release_updates_logs_redirect_collision(
    caplog: pytest.LogCaptureFixture,
) -> None:
    target_release_set = ReleaseSet(title="BLUSH")
    target_release = target_release_set.create_release(title="BLUSH")
    target_release.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RELEASE,
        "e6b9c875-f521-4261-892b-b0318a1b9b1b",
    )

    conflicting_release_set = ReleaseSet(title="Other")
    conflicting_release = conflicting_release_set.create_release(title="Other")
    conflicting_release.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RELEASE,
        "0772539c-7916-4504-bfdd-3ea8e011bb4d",
    )

    fetched_release_set = ReleaseSet(title="BLUSH")
    fetched_release = fetched_release_set.create_release(title="BLUSH")
    fetched_release.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RELEASE,
        "0772539c-7916-4504-bfdd-3ea8e011bb4d",
        provider=Provider.MUSICBRAINZ,
    )

    def fake_fetch_release_graph(
        candidate: MusicBrainzReleaseCandidate,
    ) -> MusicBrainzReleaseGraphFetchResult:
        return MusicBrainzReleaseGraphFetchResult(
            release=fetched_release,
            requested_mbid=candidate.mbid,
            resolved_mbid="0772539c-7916-4504-bfdd-3ea8e011bb4d",
            redirected=True,
        )

    def fake_fetch_candidates_from_recording(
        recording: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = recording
        return []

    def fake_fetch_candidates_from_release(
        release: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = release
        return []

    def fake_fetch_candidates_from_release_set(
        release_set: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = release_set
        return []

    def fake_fetch_candidates_from_artist(artist: object) -> list[MusicBrainzReleaseCandidate]:
        _ = artist
        return []

    fake_uow = _FakeUnitOfWork([target_release, conflicting_release])
    fake_engine = _PreparedEngine(target_release)

    def fake_uow_factory() -> ReconciliationUnitOfWork:
        return cast("ReconciliationUnitOfWork", fake_uow)

    caplog.set_level("INFO")
    result = reconcile_release_updates(
        fetch_release_graph=fake_fetch_release_graph,
        fetch_candidates_from_recording=fake_fetch_candidates_from_recording,
        fetch_candidates_from_release=fake_fetch_candidates_from_release,
        fetch_candidates_from_release_set=fake_fetch_candidates_from_release_set,
        fetch_candidates_from_artist=fake_fetch_candidates_from_artist,
        unit_of_work_factory=fake_uow_factory,
        limit=1,
        source=Provider.MUSICBRAINZ,
        engine=cast("ReconciliationEngine", fake_engine),
    )

    assert result.anchor_mismatches == 1
    assert result.applied_releases == 0
    assert fake_engine.execute_calls == 0
    assert fake_uow.repositories.external_id_redirects.saved == []
    assert result.manual_review_items[0].reason == "musicbrainz_redirect_collision"
    assert "MusicBrainz redirect collision for release BLUSH" in caplog.text


def test_reconcile_release_updates_logs_fetch_failures_and_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    target_release_set = ReleaseSet(title="Somersaults")
    target_release = target_release_set.create_release(title="Somersaults")
    target_release.add_external_id(
        ExternalNamespace.MUSICBRAINZ_RELEASE,
        "6ab3e4d6-0bc3-4162-93db-f1bbee2c0e38",
    )

    def fake_fetch_release_graph(
        candidate: MusicBrainzReleaseCandidate,
    ) -> MusicBrainzReleaseGraphFetchResult:
        raise MusicBrainzAPIError(f"404 for {candidate.mbid}")

    def fake_fetch_candidates_from_recording(
        recording: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = recording
        return []

    def fake_fetch_candidates_from_release(
        release: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = release
        return [
            cast(
                "MusicBrainzReleaseCandidate",
                SimpleNamespace(mbid="6ab3e4d6-0bc3-4162-93db-f1bbee2c0e38"),
            )
        ]

    def fake_fetch_candidates_from_release_set(
        release_set: object,
    ) -> list[MusicBrainzReleaseCandidate]:
        _ = release_set
        return []

    def fake_fetch_candidates_from_artist(artist: object) -> list[MusicBrainzReleaseCandidate]:
        _ = artist
        return []

    fake_uow = _FakeUnitOfWork([target_release])
    fake_engine = _PreparedEngine(target_release)

    def fake_uow_factory() -> ReconciliationUnitOfWork:
        return cast("ReconciliationUnitOfWork", fake_uow)

    caplog.set_level("INFO")
    result = reconcile_release_updates(
        fetch_release_graph=fake_fetch_release_graph,
        fetch_candidates_from_recording=fake_fetch_candidates_from_recording,
        fetch_candidates_from_release=fake_fetch_candidates_from_release,
        fetch_candidates_from_release_set=fake_fetch_candidates_from_release_set,
        fetch_candidates_from_artist=fake_fetch_candidates_from_artist,
        unit_of_work_factory=fake_uow_factory,
        limit=1,
        source=Provider.MUSICBRAINZ,
        engine=cast("ReconciliationEngine", fake_engine),
    )

    assert result.fetched_updates == 0
    assert result.applied_releases == 0
    assert fake_engine.execute_calls == 0
    assert "MusicBrainz fetch failed for release Somersaults" in caplog.text
