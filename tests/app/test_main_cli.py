from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sortipy.domain.model import User
from sortipy.ui import cli as main_module


def test_main_cli_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("LASTFM_API_KEY", "demo-key")
    monkeypatch.setenv("LASTFM_USER_NAME", "demo-user")
    monkeypatch.setenv("DATABASE_URI", "sqlite+pysqlite:///:memory:")

    def fake_sync(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(main_module, "sync_lastfm_play_events", fake_sync)

    main_module.main(["--user-name", "Listener"])

    assert captured["batch_size"] is None
    assert captured["max_events"] is None
    assert captured["from_timestamp"] is None
    assert captured["to_timestamp"] is None
    assert isinstance(captured["user"], User)
    assert captured["user"].display_name == "Listener"


def test_main_cli_with_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("LASTFM_API_KEY", "demo-key")
    monkeypatch.setenv("LASTFM_USER_NAME", "demo-user")
    monkeypatch.setenv("DATABASE_URI", "sqlite+pysqlite:///:memory:")

    def fake_sync(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(main_module, "sync_lastfm_play_events", fake_sync)

    main_module.main(
        [
            "--user-name",
            "Listener",
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
    assert isinstance(captured["user"], User)
    assert captured["user"].display_name == "Listener"


def test_main_cli_invalid_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_sync(*_: object, **__: object) -> None:
        return None

    monkeypatch.setattr(main_module, "sync_lastfm_play_events", fake_sync)
    monkeypatch.setenv("LASTFM_API_KEY", "demo-key")
    monkeypatch.setenv("LASTFM_USER_NAME", "demo-user")
    monkeypatch.setenv("DATABASE_URI", "sqlite+pysqlite:///:memory:")

    with pytest.raises(SystemExit) as excinfo:
        main_module.main(["--user-name", "Listener", "--start", "not-a-date"])

    assert excinfo.value.code == 2
