"""Utilities for constraining sync operations to specific time windows."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from sortipy.domain.data_integration import SyncRequest
else:  # pragma: no cover - type hint fallback
    SyncRequest = Any


class Clock(Protocol):
    def __call__(self) -> datetime: ...


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _ensure_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("Time window values must include timezone information")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class TimeWindow:
    """Describe the desired temporal bounds for a sync run."""

    start: datetime | None = None
    end: datetime | None = None
    lookback: timedelta | None = None

    def resolve(self, *, clock: Clock = _utcnow) -> tuple[datetime | None, datetime | None]:
        """Resolve the window into concrete UTC timestamps."""

        resolved_end = _ensure_aware(self.end)
        resolved_start = _ensure_aware(self.start)

        if self.lookback is not None:
            if self.lookback < timedelta(0):
                raise ValueError("Lookback duration must be non-negative")
            anchor = resolved_end or clock()
            if anchor.tzinfo is None:
                anchor = anchor.replace(tzinfo=UTC)
            anchor = anchor.astimezone(UTC)
            start_from_lookback = anchor - self.lookback
            if resolved_start is None:
                resolved_start = start_from_lookback
            else:
                resolved_start = max(resolved_start, start_from_lookback)
            if resolved_end is None:
                resolved_end = anchor

        if resolved_start and resolved_end and resolved_start > resolved_end:
            raise ValueError("Time window start must be before end")

        return resolved_start, resolved_end


def apply_time_window(
    request: SyncRequest,
    window: TimeWindow,
    *,
    clock: Clock = _utcnow,
) -> SyncRequest:
    """Return a new ``SyncRequest`` that honours the provided time window."""

    start, end = window.resolve(clock=clock)
    return replace(request, from_timestamp=start, to_timestamp=end)


__all__ = ["Clock", "TimeWindow", "apply_time_window"]
