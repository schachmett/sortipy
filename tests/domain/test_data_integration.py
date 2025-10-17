from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sortipy.domain.data_integration import SyncPlayEvents, SyncPlayEventsResult, SyncRequest
from tests.support.play_events import (
    FakePlayEventRepository,
    FakePlayEventSource,
    FakePlayEventUnitOfWork,
    make_play_event,
)


def test_sync_play_events_persists_results() -> None:
    event = make_play_event()
    repo = FakePlayEventRepository()
    service = SyncPlayEvents(
        source=FakePlayEventSource([[event]]),
        unit_of_work=lambda: FakePlayEventUnitOfWork(repo),
    )

    result = service.run(SyncRequest(batch_size=5))

    assert isinstance(result, SyncPlayEventsResult)
    assert result.stored == 1
    assert result.fetched == 1
    assert repo.items == [event]
    assert repo.items[0].timestamp == event.timestamp


def test_sync_play_events_skips_commit_when_empty() -> None:
    repo = FakePlayEventRepository()
    uow = FakePlayEventUnitOfWork(repo)
    service = SyncPlayEvents(
        source=FakePlayEventSource([[]]),
        unit_of_work=lambda: uow,
    )

    result = service.run()

    assert result.stored == 0
    assert repo.items == []
    assert uow.committed is False


def test_sync_play_events_skips_existing_timestamps() -> None:
    event = make_play_event()
    repo = FakePlayEventRepository([event])
    service = SyncPlayEvents(
        source=FakePlayEventSource([[event]]),
        unit_of_work=lambda: FakePlayEventUnitOfWork(repo),
    )

    result = service.run()

    assert result.stored == 0
    assert repo.items == [event]


def test_sync_play_events_respects_from_timestamp() -> None:
    older = make_play_event("Old")
    older.timestamp = older.timestamp.replace(microsecond=0)
    newer = make_play_event("New")
    newer.timestamp = older.timestamp + timedelta(seconds=60)
    repo = FakePlayEventRepository([older])
    fake_source = FakePlayEventSource([[older, newer]])
    service = SyncPlayEvents(
        source=fake_source,
        unit_of_work=lambda: FakePlayEventUnitOfWork(repo),
    )

    result = service.run(SyncRequest(from_timestamp=older.timestamp))

    assert result.stored == 1
    assert newer in repo.items
    assert fake_source.calls[0]["since"] == older.timestamp


def test_sync_play_events_returns_now_playing_without_persisting() -> None:
    in_progress = make_play_event("Now Playing")
    logged = make_play_event("Logged")
    repo = FakePlayEventRepository()
    fake_source = FakePlayEventSource([[logged]], now_playing=in_progress)
    service = SyncPlayEvents(
        source=fake_source,
        unit_of_work=lambda: FakePlayEventUnitOfWork(repo),
    )

    result = service.run()

    assert result.now_playing is in_progress
    assert in_progress not in repo.items
    assert logged in repo.items


def test_sync_play_events_respects_to_timestamp_upper_bound() -> None:
    base_time = datetime.now(tz=UTC).replace(microsecond=0)
    within_window = make_play_event("Within", timestamp=base_time)
    beyond_window = make_play_event("Beyond", timestamp=base_time + timedelta(seconds=60))
    repo = FakePlayEventRepository()
    fake_source = FakePlayEventSource([[within_window, beyond_window]])
    service = SyncPlayEvents(
        source=fake_source,
        unit_of_work=lambda: FakePlayEventUnitOfWork(repo),
    )

    window_end = base_time + timedelta(seconds=10)
    result = service.run(SyncRequest(to_timestamp=window_end))

    assert result.stored == 1
    assert within_window in repo.items
    assert beyond_window not in repo.items
