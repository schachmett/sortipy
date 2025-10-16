from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from sortipy.app import sync_lastfm_scrobbles
from sortipy.domain.data_integration import ScrobbleUnitOfWork, SyncRequest, SyncScrobblesResult
from tests.support.scrobbles import (
    FakeScrobbleRepository,
    FakeScrobbleSource,
    FakeScrobbleUnitOfWork,
    make_scrobble,
)


class MonkeyPatch(Protocol):
    def setattr(self, target: str, value: object) -> None: ...


def test_sync_lastfm_scrobbles_orchestrates_dependencies(monkeypatch: MonkeyPatch) -> None:
    startup_called = False

    def fake_startup() -> None:
        nonlocal startup_called
        startup_called = True

    monkeypatch.setattr("sortipy.app.startup", fake_startup)

    scrobble = make_scrobble(
        "Example Track",
        timestamp=datetime.now(tz=UTC).replace(microsecond=0),
    )
    source = FakeScrobbleSource([[scrobble]])
    repository = FakeScrobbleRepository()

    def factory() -> ScrobbleUnitOfWork:
        return FakeScrobbleUnitOfWork(repository)

    result = sync_lastfm_scrobbles(
        SyncRequest(limit=1),
        source=source,
        unit_of_work_factory=factory,
    )

    assert startup_called is True
    assert isinstance(result, SyncScrobblesResult)
    assert result.stored == 1
    assert repository.items == [scrobble]
    assert source.calls[0][1] == 1  # limit passed through


def test_sync_lastfm_scrobbles_respects_existing_entries(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("sortipy.app.startup", lambda: None)

    base_time = datetime.now(tz=UTC).replace(microsecond=0)
    existing = make_scrobble("Existing", timestamp=base_time)
    newer = make_scrobble("Newer", timestamp=base_time + timedelta(seconds=60))

    repository = FakeScrobbleRepository([existing])
    source = FakeScrobbleSource([[existing, newer]])

    def factory() -> ScrobbleUnitOfWork:
        return FakeScrobbleUnitOfWork(repository)

    result = sync_lastfm_scrobbles(
        SyncRequest(limit=2),
        source=source,
        unit_of_work_factory=factory,
    )

    assert result.stored == 1
    assert newer in repository.items
    assert existing in repository.items


def test_sync_lastfm_scrobbles_respects_request_bounds(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("sortipy.app.startup", lambda: None)

    now = datetime(2025, 3, 5, 12, tzinfo=UTC)
    lookback = timedelta(hours=2)
    older = make_scrobble("Older", timestamp=now - lookback - timedelta(minutes=10))
    recent = make_scrobble("Recent", timestamp=now - timedelta(minutes=30))

    repository = FakeScrobbleRepository()
    source = FakeScrobbleSource([[older, recent]])

    def factory() -> ScrobbleUnitOfWork:
        return FakeScrobbleUnitOfWork(repository)

    request = SyncRequest(
        limit=5,
        from_timestamp=now - lookback,
        to_timestamp=now,
    )

    result = sync_lastfm_scrobbles(
        request,
        source=source,
        unit_of_work_factory=factory,
    )

    assert result.stored == 1
    assert repository.items == [recent]

    first_call = source.calls[0]
    expected_from = int((now - lookback).timestamp()) + 1
    expected_to = int(now.timestamp())
    assert first_call[2] == expected_from
    assert first_call[3] == expected_to
