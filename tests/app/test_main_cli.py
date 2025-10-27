from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sortipy import main as main_module
from sortipy.domain.data_integration import DEFAULT_SYNC_BATCH_SIZE


def test_main_cli_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_sync(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(main_module, "sync_lastfm_play_events", fake_sync)

    main_module.main([])

    assert captured["batch_size"] == DEFAULT_SYNC_BATCH_SIZE
    assert captured["max_events"] is None
    assert captured["from_timestamp"] is None
    assert captured["to_timestamp"] is None


def test_main_cli_with_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_sync(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(main_module, "sync_lastfm_play_events", fake_sync)

    main_module.main(
        [
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


def test_main_cli_invalid_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_sync(*_: object, **__: object) -> None:
        return None

    monkeypatch.setattr(main_module, "sync_lastfm_play_events", fake_sync)

    with pytest.raises(SystemExit) as excinfo:
        main_module.main(["--start", "not-a-date"])

    assert excinfo.value.code == 2
