from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from sortipy.domain.reconciliation import ApplyCounters, LastfmReconciliationResult
from sortipy.ui import cli as main_module


def test_main_cli_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("LASTFM_API_KEY", "demo-key")
    monkeypatch.setenv("LASTFM_USER_NAME", "demo-user")
    monkeypatch.setenv("DATABASE_URI", "sqlite+pysqlite:///:memory:")

    def fake_sync(**kwargs: object) -> LastfmReconciliationResult:
        captured.update(kwargs)
        return _lastfm_result()

    monkeypatch.setattr(main_module, "reconcile_lastfm_play_events", fake_sync)

    main_module.main(["reconcile", "lastfm", "--user-id", "00000000-0000-0000-0000-000000000001"])

    assert captured["batch_size"] is None
    assert captured["max_events"] is None
    assert captured["from_timestamp"] is None
    assert captured["to_timestamp"] is None
    assert captured["user_id"] == UUID("00000000-0000-0000-0000-000000000001")


def test_main_cli_with_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("LASTFM_API_KEY", "demo-key")
    monkeypatch.setenv("LASTFM_USER_NAME", "demo-user")
    monkeypatch.setenv("DATABASE_URI", "sqlite+pysqlite:///:memory:")

    def fake_sync(**kwargs: object) -> LastfmReconciliationResult:
        captured.update(kwargs)
        return _lastfm_result()

    monkeypatch.setattr(main_module, "reconcile_lastfm_play_events", fake_sync)

    main_module.main(
        [
            "reconcile",
            "lastfm",
            "--user-id",
            "00000000-0000-0000-0000-000000000001",
            "--batch-size",
            "50",
            "--max-events",
            "3",
            "--start",
            "2025-01-01T03:00:00+03:00",
            "--end",
            "2025-01-02T00:00:00Z",
            "--lookback-hours",
            "2.5",
        ]
    )

    assert captured["batch_size"] == 50
    assert captured["max_events"] == 3
    assert captured["from_timestamp"] == datetime(2025, 1, 1, 21, 30, tzinfo=UTC)
    assert captured["to_timestamp"] == datetime(2025, 1, 2, 0, 0, tzinfo=UTC)
    assert captured["user_id"] == UUID("00000000-0000-0000-0000-000000000001")


def test_main_cli_invalid_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_sync(*_: object, **__: object) -> LastfmReconciliationResult:
        return _lastfm_result()

    monkeypatch.setattr(main_module, "reconcile_lastfm_play_events", fake_sync)
    monkeypatch.setenv("LASTFM_API_KEY", "demo-key")
    monkeypatch.setenv("LASTFM_USER_NAME", "demo-user")
    monkeypatch.setenv("DATABASE_URI", "sqlite+pysqlite:///:memory:")

    with pytest.raises(SystemExit) as excinfo:
        main_module.main(
            [
                "reconcile",
                "lastfm",
                "--user-id",
                "00000000-0000-0000-0000-000000000001",
                "--start",
                "not-a-date",
            ]
        )

    assert excinfo.value.code == 2


def _lastfm_result() -> LastfmReconciliationResult:
    return LastfmReconciliationResult(
        fetched=0,
        persisted_entities=0,
        persisted_sidecars=0,
        entities=ApplyCounters(),
        associations=ApplyCounters(),
        links=ApplyCounters(),
        manual_review_items=[],
        stored_events=0,
    )
