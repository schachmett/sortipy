from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Protocol

from sortipy.app import sync_lastfm_play_events
from sortipy.config.http_resilience import CacheConfig, RateLimit, ResilienceConfig
from sortipy.config.lastfm import LASTFM_BASE_URL, LASTFM_TIMEOUT_SECONDS, LastFmConfig
from sortipy.config.storage import DatabaseConfig
from sortipy.domain.data_integration import SyncPlayEventsResult
from sortipy.domain.model import User
from tests.helpers.play_events import (
    FakeIngestUnitOfWork,
    FakePlayEventRepository,
    FakePlayEventSource,
    make_play_event,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sortipy.domain.ingest_pipeline.ingest_ports import PlayEventSyncUnitOfWork
    from sortipy.domain.ports.fetching import PlayEventFetchResult


class MonkeyPatch(Protocol):
    def setattr(self, target: str, value: object) -> None: ...


def _make_lastfm_config(**_: object) -> LastFmConfig:
    resilience = ResilienceConfig(
        name="lastfm",
        base_url=LASTFM_BASE_URL,
        timeout_seconds=LASTFM_TIMEOUT_SECONDS,
        ratelimit=RateLimit(max_calls=4, per_seconds=1.0),
        cache=CacheConfig(backend="memory"),
    )
    return LastFmConfig(api_key="demo", user_name="demo-user", resilience=resilience)


def _patch_lastfm_sync(
    monkeypatch: MonkeyPatch,
    *,
    source: FakePlayEventSource,
    repository: FakePlayEventRepository,
) -> None:
    def fake_fetch_play_events(
        *,
        config: LastFmConfig,
        user: User,
        batch_size: int = 200,
        since: datetime | None = None,
        until: datetime | None = None,
        max_events: int | None = None,
    ) -> PlayEventFetchResult:
        _ = config
        return source(
            user=user,
            batch_size=batch_size,
            since=since,
            until=until,
            max_events=max_events,
        )

    def fake_uow_factory(**_: object) -> Callable[[], PlayEventSyncUnitOfWork]:
        return lambda: FakeIngestUnitOfWork(repository)

    monkeypatch.setattr("sortipy.app.fetch_play_events", fake_fetch_play_events)
    monkeypatch.setattr("sortipy.app.create_unit_of_work_factory", fake_uow_factory)
    monkeypatch.setattr("sortipy.app.get_lastfm_config", _make_lastfm_config)
    monkeypatch.setattr(
        "sortipy.app.get_database_config",
        lambda: DatabaseConfig(uri="sqlite+pysqlite:///:memory:"),
    )


def test_sync_lastfm_play_events_orchestrates_dependencies(monkeypatch: MonkeyPatch) -> None:
    play_event = make_play_event(
        "Example Track",
        timestamp=datetime.now(tz=UTC).replace(microsecond=0),
    )
    user = User(display_name="Listener")
    source = FakePlayEventSource([[play_event]])
    repository = FakePlayEventRepository()

    _patch_lastfm_sync(monkeypatch, source=source, repository=repository)

    result = sync_lastfm_play_events(
        user=user,
        batch_size=1,
    )

    assert isinstance(result, SyncPlayEventsResult)
    assert result.stored == 1
    assert repository.items == [play_event]
    assert source.calls[0]["batch_size"] == 1
    assert source.calls[0]["user"] is user


def test_sync_lastfm_play_events_respects_existing_entries(monkeypatch: MonkeyPatch) -> None:
    base_time = datetime.now(tz=UTC).replace(microsecond=0)
    existing = make_play_event("Existing", timestamp=base_time)
    newer = make_play_event("Newer", timestamp=base_time + timedelta(seconds=60))
    user = User(display_name="Listener")

    repository = FakePlayEventRepository([existing])
    source = FakePlayEventSource([[existing, newer]])
    _patch_lastfm_sync(monkeypatch, source=source, repository=repository)

    result = sync_lastfm_play_events(
        user=user,
        batch_size=2,
    )

    assert result.stored == 1
    assert newer in repository.items
    assert existing in repository.items


def test_sync_lastfm_play_events_respects_request_bounds(monkeypatch: MonkeyPatch) -> None:
    now = datetime(2025, 3, 5, 12, tzinfo=UTC)
    lookback = timedelta(hours=2)
    older = make_play_event("Older", timestamp=now - lookback - timedelta(minutes=10))
    recent = make_play_event("Recent", timestamp=now - timedelta(minutes=30))
    user = User(display_name="Listener")

    repository = FakePlayEventRepository()
    source = FakePlayEventSource([[older, recent]])
    _patch_lastfm_sync(monkeypatch, source=source, repository=repository)

    result = sync_lastfm_play_events(
        user=user,
        batch_size=5,
        from_timestamp=now - lookback,
        to_timestamp=now,
    )

    assert result.stored == 1
    assert repository.items == [recent]

    recorded_call = source.calls[0]
    assert recorded_call["since"] == now - lookback
    assert recorded_call["until"] == now
