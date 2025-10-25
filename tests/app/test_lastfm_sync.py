from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Protocol

from sortipy.app import sync_lastfm_play_events
from sortipy.domain.data_integration import SyncPlayEventsResult
from tests.helpers.play_events import (
    FakePlayEventRepository,
    FakePlayEventSource,
    FakePlayEventUnitOfWork,
    make_play_event,
)

if TYPE_CHECKING:
    from sortipy.domain.ports.unit_of_work import PlayEventUnitOfWork


class MonkeyPatch(Protocol):
    def setattr(self, target: str, value: object) -> None: ...


def test_sync_lastfm_play_events_orchestrates_dependencies(monkeypatch: MonkeyPatch) -> None:
    startup_called = False

    def fake_startup() -> None:
        nonlocal startup_called
        startup_called = True

    monkeypatch.setattr("sortipy.app.startup", fake_startup)

    play_event = make_play_event(
        "Example Track",
        timestamp=datetime.now(tz=UTC).replace(microsecond=0),
    )
    source = FakePlayEventSource([[play_event]])
    repository = FakePlayEventRepository()

    def factory() -> PlayEventUnitOfWork:
        return FakePlayEventUnitOfWork(repository)

    result = sync_lastfm_play_events(
        source=source,
        unit_of_work_factory=factory,
        batch_size=1,
    )

    assert startup_called is True
    assert isinstance(result, SyncPlayEventsResult)
    assert result.stored == 1
    assert repository.items == [play_event]
    assert source.calls[0]["batch_size"] == 1


def test_sync_lastfm_play_events_respects_existing_entries(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("sortipy.app.startup", lambda: None)

    base_time = datetime.now(tz=UTC).replace(microsecond=0)
    existing = make_play_event("Existing", timestamp=base_time)
    newer = make_play_event("Newer", timestamp=base_time + timedelta(seconds=60))

    repository = FakePlayEventRepository([existing])
    source = FakePlayEventSource([[existing, newer]])

    def factory() -> PlayEventUnitOfWork:
        return FakePlayEventUnitOfWork(repository)

    result = sync_lastfm_play_events(
        source=source,
        unit_of_work_factory=factory,
        batch_size=2,
    )

    assert result.stored == 1
    assert newer in repository.items
    assert existing in repository.items


def test_sync_lastfm_play_events_respects_request_bounds(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("sortipy.app.startup", lambda: None)

    now = datetime(2025, 3, 5, 12, tzinfo=UTC)
    lookback = timedelta(hours=2)
    older = make_play_event("Older", timestamp=now - lookback - timedelta(minutes=10))
    recent = make_play_event("Recent", timestamp=now - timedelta(minutes=30))

    repository = FakePlayEventRepository()
    source = FakePlayEventSource([[older, recent]])

    def factory() -> PlayEventUnitOfWork:
        return FakePlayEventUnitOfWork(repository)

    result = sync_lastfm_play_events(
        source=source,
        unit_of_work_factory=factory,
        batch_size=5,
        from_timestamp=now - lookback,
        to_timestamp=now,
    )

    assert result.stored == 1
    assert repository.items == [recent]

    recorded_call = source.calls[0]
    assert recorded_call["since"] == now - lookback
    assert recorded_call["until"] == now
