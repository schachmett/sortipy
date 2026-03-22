from __future__ import annotations

from tests.helpers.library_items import (
    FakeIngestUnitOfWork,
    FakeLibraryItemRepository,
    FakeLibraryItemSource,
    make_artist_library_item,
    make_reconciliation_uow_factory,
    make_recording_library_item,
    make_release_set_library_item,
)

from sortipy.domain.model import User
from sortipy.domain.reconciliation import (
    LibraryItemReconciliationRequest,
    SpotifyLibraryReconciliationResult,
    reconcile_library_items,
)


def test_reconcile_library_items_persists_results() -> None:
    user = User(display_name="Library User")
    items = [
        make_recording_library_item(user),
        make_release_set_library_item(user),
        make_artist_library_item(user),
    ]
    fetcher = FakeLibraryItemSource(items)
    uow = FakeIngestUnitOfWork(FakeLibraryItemRepository())

    result = reconcile_library_items(
        request=LibraryItemReconciliationRequest(batch_size=10),
        fetcher=fetcher,
        unit_of_work_factory=make_reconciliation_uow_factory(uow),
        user=user,
    )

    assert isinstance(result, SpotifyLibraryReconciliationResult)
    assert result.fetched == 3
    assert result.stored_items == 3
    assert uow.committed is True


def test_reconcile_library_items_skips_commit_when_empty() -> None:
    user = User(display_name="Library User")
    fetcher = FakeLibraryItemSource([])
    uow = FakeIngestUnitOfWork(FakeLibraryItemRepository())

    result = reconcile_library_items(
        request=LibraryItemReconciliationRequest(batch_size=10),
        fetcher=fetcher,
        unit_of_work_factory=make_reconciliation_uow_factory(uow),
        user=user,
    )

    assert result.stored_items == 0
    assert result.fetched == 0
    assert uow.committed is False
