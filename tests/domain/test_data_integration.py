from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sortipy.domain.data_integration import (
    SyncRequest,
    SyncScrobbles,
    SyncScrobblesResult,
)
from tests.support.scrobbles import (
    FakeScrobbleRepository,
    FakeScrobbleSource,
    FakeScrobbleUnitOfWork,
    make_scrobble,
)


def test_sync_scrobbles_persists_results() -> None:
    scrobble = make_scrobble()
    repo = FakeScrobbleRepository()
    service = SyncScrobbles(
        source=FakeScrobbleSource([[scrobble]]),
        unit_of_work=lambda: FakeScrobbleUnitOfWork(repo),
    )

    result = service.run(SyncRequest(limit=5))

    assert isinstance(result, SyncScrobblesResult)
    assert result.stored == 1
    assert result.pages_processed == 1
    assert repo.items == [scrobble]
    assert repo.items[0].timestamp == scrobble.timestamp


def test_sync_scrobbles_skips_commit_when_empty() -> None:
    repo = FakeScrobbleRepository()
    uow = FakeScrobbleUnitOfWork(repo)
    service = SyncScrobbles(
        source=FakeScrobbleSource([[]]),
        unit_of_work=lambda: uow,
    )

    result = service.run()

    assert result.stored == 0
    assert repo.items == []
    assert uow.committed is False


def test_sync_scrobbles_skips_existing_timestamps() -> None:
    scrobble = make_scrobble()
    repo = FakeScrobbleRepository([scrobble])
    service = SyncScrobbles(
        source=FakeScrobbleSource([[scrobble]]),
        unit_of_work=lambda: FakeScrobbleUnitOfWork(repo),
    )

    result = service.run()

    assert result.stored == 0
    assert repo.items == [scrobble]


def test_sync_scrobbles_respects_from_timestamp() -> None:
    scrobble_old = make_scrobble("Old")
    scrobble_old.timestamp = scrobble_old.timestamp.replace(microsecond=0)
    scrobble_new = make_scrobble("New")
    scrobble_new.timestamp = scrobble_old.timestamp + timedelta(seconds=60)
    repo = FakeScrobbleRepository()
    repo.add(scrobble_old)
    fake_source = FakeScrobbleSource([[scrobble_old, scrobble_new]])
    service = SyncScrobbles(
        source=fake_source,
        unit_of_work=lambda: FakeScrobbleUnitOfWork(repo),
    )

    result = service.run()

    assert result.stored == 1
    assert scrobble_new in repo.items
    assert fake_source.calls[0][2] is not None


def test_sync_scrobbles_returns_now_playing_without_persisting() -> None:
    in_progress = make_scrobble("Now Playing")
    scrobble = make_scrobble("Logged")
    repo = FakeScrobbleRepository()
    fake_source = FakeScrobbleSource([[scrobble]], now_playing=[in_progress])
    service = SyncScrobbles(
        source=fake_source,
        unit_of_work=lambda: FakeScrobbleUnitOfWork(repo),
    )

    result = service.run()

    assert result.now_playing is in_progress
    assert in_progress not in repo.items
    assert scrobble in repo.items


def test_sync_scrobbles_resumes_across_pages() -> None:
    base_time = datetime.now(tz=UTC).replace(microsecond=0)
    existing = make_scrobble("Existing")
    existing.timestamp = base_time
    first_new = make_scrobble("First New")
    first_new.timestamp = base_time + timedelta(seconds=30)
    second_new = make_scrobble("Second New")
    second_new.timestamp = base_time + timedelta(seconds=60)
    repo = FakeScrobbleRepository([existing])
    fake_source = FakeScrobbleSource([[first_new], [second_new]])
    service = SyncScrobbles(
        source=fake_source,
        unit_of_work=lambda: FakeScrobbleUnitOfWork(repo),
    )

    result = service.run(SyncRequest(limit=1))

    timestamps = {item.timestamp for item in repo.items}
    assert timestamps == {existing.timestamp, first_new.timestamp, second_new.timestamp}
    assert result.stored == 2
    assert result.pages_processed == 2
    assert fake_source.calls[0][0] == 1
    assert fake_source.calls[0][2] is not None
    assert fake_source.calls[1][0] == 2
    assert fake_source.calls[1][2] is None


def test_sync_scrobbles_respects_to_timestamp_upper_bound() -> None:
    base_time = datetime.now(tz=UTC).replace(microsecond=0)
    within_window = make_scrobble("Within", timestamp=base_time)
    beyond_window = make_scrobble("Beyond", timestamp=base_time + timedelta(seconds=60))
    repo = FakeScrobbleRepository()
    fake_source = FakeScrobbleSource([[within_window, beyond_window]])
    service = SyncScrobbles(
        source=fake_source,
        unit_of_work=lambda: FakeScrobbleUnitOfWork(repo),
    )

    window_end = base_time + timedelta(seconds=10)
    result = service.run(SyncRequest(to_timestamp=window_end))

    assert result.stored == 1
    assert within_window in repo.items
    assert beyond_window not in repo.items
