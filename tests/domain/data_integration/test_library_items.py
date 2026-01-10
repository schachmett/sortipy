from __future__ import annotations

from sortipy.domain.data_integration import SyncLibraryItemsResult, sync_library_items
from sortipy.domain.model import User
from tests.helpers.library_items import (
    FakeLibraryItemSource,
    make_artist_library_item,
    make_recording_library_item,
    make_release_set_library_item,
)
from tests.helpers.play_events import FakeIngestUnitOfWork, FakePlayEventRepository


def test_sync_library_items_persists_results() -> None:
    user = User(display_name="Library User")
    items = [
        make_recording_library_item(user),
        make_release_set_library_item(user),
        make_artist_library_item(user),
    ]
    fetcher = FakeLibraryItemSource(items)
    uow = FakeIngestUnitOfWork(FakePlayEventRepository())

    result = sync_library_items(
        fetcher=fetcher,
        unit_of_work_factory=lambda: uow,
        user=user,
        batch_size=10,
    )

    assert isinstance(result, SyncLibraryItemsResult)
    assert result.fetched == 3
    assert result.stored == 3
    assert uow.committed is True


def test_sync_library_items_skips_commit_when_empty() -> None:
    user = User(display_name="Library User")
    fetcher = FakeLibraryItemSource([])
    uow = FakeIngestUnitOfWork(FakePlayEventRepository())

    result = sync_library_items(
        fetcher=fetcher,
        unit_of_work_factory=lambda: uow,
        user=user,
    )

    assert result.stored == 0
    assert result.fetched == 0
    assert uow.committed is False
