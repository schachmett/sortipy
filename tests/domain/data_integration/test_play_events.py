from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sortipy.domain.data_integration import SyncPlayEventsResult, sync_play_events
from sortipy.domain.model import User
from tests.helpers.play_events import (
    FakeIngestUnitOfWork,
    FakePlayEventRepository,
    FakePlayEventSource,
    make_play_event,
)


def test_sync_play_events_persists_results() -> None:
    event = make_play_event()
    user = event.user
    repo = FakePlayEventRepository()
    result = sync_play_events(
        fetcher=FakePlayEventSource([[event]]),
        user=user,
        unit_of_work_factory=lambda: FakeIngestUnitOfWork(repo),
        batch_size=5,
    )

    assert isinstance(result, SyncPlayEventsResult)
    assert result.stored == 1
    assert result.fetched == 1
    assert repo.items == [event]
    assert repo.items[0].played_at == event.played_at


def test_sync_play_events_skips_commit_when_empty() -> None:
    repo = FakePlayEventRepository()
    uow = FakeIngestUnitOfWork(repo)
    user = User(display_name="Listener")
    result = sync_play_events(
        fetcher=FakePlayEventSource([[]]),
        user=user,
        unit_of_work_factory=lambda: uow,
    )

    assert result.stored == 0
    assert repo.items == []
    assert uow.committed is False


def test_sync_play_events_skips_existing_timestamps() -> None:
    event = make_play_event()
    user = event.user
    repo = FakePlayEventRepository([event])
    result = sync_play_events(
        fetcher=FakePlayEventSource([[event]]),
        user=user,
        unit_of_work_factory=lambda: FakeIngestUnitOfWork(repo),
    )

    assert result.stored == 0
    assert repo.items == [event]


def test_sync_play_events_respects_from_timestamp() -> None:
    older = make_play_event("Old")
    older.played_at = older.played_at.replace(microsecond=0)
    newer = make_play_event("New")
    newer.played_at = older.played_at + timedelta(seconds=60)
    user = User(display_name="Listener")
    repo = FakePlayEventRepository([older])
    fake_source = FakePlayEventSource([[older, newer]])
    result = sync_play_events(
        fetcher=fake_source,
        user=user,
        unit_of_work_factory=lambda: FakeIngestUnitOfWork(repo),
        from_timestamp=older.played_at,
    )

    assert result.stored == 1
    assert newer in repo.items
    assert fake_source.calls[0]["since"] == older.played_at


def test_sync_play_events_returns_now_playing_without_persisting() -> None:
    in_progress = make_play_event("Now Playing")
    logged = make_play_event("Logged")
    user = User(display_name="Listener")
    repo = FakePlayEventRepository()
    fake_source = FakePlayEventSource([[logged]], now_playing=in_progress)
    result = sync_play_events(
        fetcher=fake_source,
        user=user,
        unit_of_work_factory=lambda: FakeIngestUnitOfWork(repo),
    )

    assert result.now_playing is in_progress
    assert in_progress not in repo.items
    assert logged in repo.items


def test_sync_play_events_respects_to_timestamp_upper_bound() -> None:
    base_time = datetime.now(tz=UTC).replace(microsecond=0)
    within_window = make_play_event("Within", timestamp=base_time)
    beyond_window = make_play_event("Beyond", timestamp=base_time + timedelta(seconds=60))
    user = User(display_name="Listener")
    repo = FakePlayEventRepository()
    fake_source = FakePlayEventSource([[within_window, beyond_window]])
    window_end = base_time + timedelta(seconds=10)
    result = sync_play_events(
        fetcher=fake_source,
        user=user,
        unit_of_work_factory=lambda: FakeIngestUnitOfWork(repo),
        to_timestamp=window_end,
    )

    assert result.stored == 1
    assert within_window in repo.items
    assert beyond_window not in repo.items


def test_sync_play_events_reports_latest_timestamp_from_new_data() -> None:
    base_time = datetime.now(tz=UTC).replace(microsecond=0)
    first = make_play_event("First", timestamp=base_time)
    second = make_play_event("Second", timestamp=base_time + timedelta(seconds=30))
    user = User(display_name="Listener")
    repo = FakePlayEventRepository()
    result = sync_play_events(
        fetcher=FakePlayEventSource([[first, second]]),
        user=user,
        unit_of_work_factory=lambda: FakeIngestUnitOfWork(repo),
    )

    assert result.latest_timestamp == second.played_at


def test_sync_play_events_uses_repository_latest_timestamp_when_request_missing_from() -> None:
    base_time = datetime.now(tz=UTC).replace(microsecond=0)
    existing = make_play_event("Existing", timestamp=base_time)
    repo = FakePlayEventRepository([existing])
    next_event = make_play_event("Next", timestamp=base_time + timedelta(seconds=25))
    user = User(display_name="Listener")
    fake_source = FakePlayEventSource([[next_event]])
    result = sync_play_events(
        fetcher=fake_source,
        user=user,
        unit_of_work_factory=lambda: FakeIngestUnitOfWork(repo),
    )

    assert result.stored == 1
    assert fake_source.calls[0]["since"] == existing.played_at
    assert repo.items[-1] is next_event


def test_sync_play_events_honours_max_events_limit() -> None:
    base_time = datetime.now(tz=UTC).replace(microsecond=0)
    events = [
        make_play_event(f"Track {index}", timestamp=base_time + timedelta(seconds=index * 5))
        for index in range(3)
    ]
    user = User(display_name="Listener")
    repo = FakePlayEventRepository()
    fake_source = FakePlayEventSource([events])
    result = sync_play_events(
        fetcher=fake_source,
        user=user,
        unit_of_work_factory=lambda: FakeIngestUnitOfWork(repo),
        max_events=2,
    )

    assert result.stored == 2
    assert result.fetched == 2
    assert fake_source.calls[0]["max_events"] == 2


def test_sync_play_events_skips_commit_when_upper_bound_filters_all_events() -> None:
    base_time = datetime.now(tz=UTC).replace(microsecond=0)
    out_of_range = make_play_event("Too Late", timestamp=base_time + timedelta(seconds=60))
    user = User(display_name="Listener")
    repo = FakePlayEventRepository()
    uow = FakeIngestUnitOfWork(repo)
    window_end = base_time
    result = sync_play_events(
        fetcher=FakePlayEventSource([[out_of_range]]),
        user=user,
        unit_of_work_factory=lambda: uow,
        to_timestamp=window_end,
    )

    assert result.stored == 0
    assert uow.committed is False
    assert repo.items == []


def test_sync_play_events_deduplicates_events_with_same_timestamp_in_batch() -> None:
    base_time = datetime.now(tz=UTC).replace(microsecond=0)
    duplicate_a = make_play_event("Dup A", timestamp=base_time)
    duplicate_b = make_play_event("Dup B", timestamp=base_time)
    user = User(display_name="Listener")
    repo = FakePlayEventRepository()
    result = sync_play_events(
        fetcher=FakePlayEventSource([[duplicate_a, duplicate_b]]),
        user=user,
        unit_of_work_factory=lambda: FakeIngestUnitOfWork(repo),
    )

    assert result.stored == 1
    assert len(repo.items) == 1
    assert repo.items[0].played_at == base_time
