from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sortipy.domain.data_integration import SyncRequest
from sortipy.domain.time_windows import Clock, TimeWindow, apply_time_window


def _make_clock(reference: datetime) -> Clock:
    def _clock() -> datetime:
        return reference

    return _clock


def test_time_window_with_lookback_produces_start_and_end() -> None:
    now = datetime(2025, 1, 1, 12, tzinfo=UTC)
    window = TimeWindow(lookback=timedelta(hours=6))

    start, end = window.resolve(clock=_make_clock(now))

    assert start == datetime(2025, 1, 1, 6, tzinfo=UTC)
    assert end == now


def test_time_window_combines_start_and_lookback() -> None:
    now = datetime(2025, 1, 10, tzinfo=UTC)
    start = datetime(2025, 1, 8, tzinfo=UTC)
    window = TimeWindow(start=start, lookback=timedelta(days=5))

    resolved_start, resolved_end = window.resolve(clock=_make_clock(now))

    assert resolved_start == start
    assert resolved_end == now


def test_time_window_with_end_and_lookback_anchors_to_end() -> None:
    end = datetime(2025, 2, 1, tzinfo=UTC)
    window = TimeWindow(end=end, lookback=timedelta(days=2))

    resolved_start, resolved_end = window.resolve()

    assert resolved_start == datetime(2025, 1, 30, tzinfo=UTC)
    assert resolved_end == end


def test_time_window_rejects_naive_datetimes() -> None:
    start = datetime(2025, 1, 1, 12, tzinfo=UTC).replace(tzinfo=None)
    end = datetime(2025, 1, 2, 12, tzinfo=UTC).replace(tzinfo=None)
    window = TimeWindow(start=start, end=end)

    with pytest.raises(ValueError, match="timezone information"):
        window.resolve()


def test_time_window_rejects_inverted_bounds() -> None:
    start = datetime(2025, 1, 2, tzinfo=UTC)
    end = datetime(2025, 1, 1, tzinfo=UTC)
    window = TimeWindow(start=start, end=end)

    with pytest.raises(ValueError, match="before end"):
        window.resolve()


def test_apply_time_window_updates_sync_request() -> None:
    now = datetime(2025, 3, 15, 15, tzinfo=UTC)
    window = TimeWindow(lookback=timedelta(hours=1))
    base = SyncRequest(limit=50)

    result = apply_time_window(base, window, clock=_make_clock(now))

    assert result.limit == 50
    assert result.from_timestamp == datetime(2025, 3, 15, 14, tzinfo=UTC)
    assert result.to_timestamp == now
