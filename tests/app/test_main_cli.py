from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sortipy.domain.data_integration import SyncRequest


def test_main_cli_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from sortipy import main as main_module

    captured: dict[str, object] = {}

    def fake_sync(request: SyncRequest, **kwargs: object) -> None:
        captured["request"] = request
        captured["kwargs"] = kwargs

    monkeypatch.setattr(main_module, "sync_lastfm_scrobbles", fake_sync)

    main_module.main([])

    assert isinstance(captured["request"], SyncRequest)
    request = captured["request"]
    assert request.limit == SyncRequest().limit
    assert request.max_pages is None
    assert captured["kwargs"] == {}


def test_main_cli_with_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    from sortipy import main as main_module

    captured: dict[str, object] = {}

    def fake_sync(request: SyncRequest, **kwargs: object) -> None:
        captured["request"] = request
        captured["kwargs"] = kwargs

    monkeypatch.setattr(main_module, "sync_lastfm_scrobbles", fake_sync)

    main_module.main(
        [
            "--limit",
            "50",
            "--max-pages",
            "3",
            "--start",
            "2025-01-01T03:00:00+03:00",
            "--end",
            "2025-01-02T00:00:00Z",
            "--lookback-hours",
            "2.5",
        ]
    )

    request = captured["request"]
    assert isinstance(request, SyncRequest)
    assert request.limit == 50
    assert request.max_pages == 3
    assert request.from_timestamp == datetime(2025, 1, 1, 21, 30, tzinfo=UTC)
    assert request.to_timestamp == datetime(2025, 1, 2, 0, 0, tzinfo=UTC)
    assert captured["kwargs"] == {}


def test_main_cli_invalid_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    from sortipy import main as main_module

    def fake_sync(*_: object, **__: object) -> None:
        return None

    monkeypatch.setattr(main_module, "sync_lastfm_scrobbles", fake_sync)

    with pytest.raises(SystemExit) as excinfo:
        main_module.main(["--start", "not-a-date"])

    assert excinfo.value.code == 2
