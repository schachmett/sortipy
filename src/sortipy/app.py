"""Application orchestration entry points."""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from sortipy.adapters.lastfm import HttpLastFmPlayEventSource
from sortipy.common.unit_of_work import get_unit_of_work, startup
from sortipy.domain.data_integration import (
    PlayEventSource,
    PlayEventUnitOfWork,
    SyncPlayEvents,
    SyncPlayEventsResult,
    SyncRequest,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    UnitOfWorkFactory = Callable[[], PlayEventUnitOfWork]
else:  # pragma: no cover - runtime placeholder for type checking
    UnitOfWorkFactory = object


log = getLogger(__name__)


def sync_lastfm_play_events(
    request: SyncRequest | None = None,
    *,
    source: PlayEventSource | None = None,
    unit_of_work_factory: UnitOfWorkFactory | None = None,
) -> SyncPlayEventsResult:
    """Synchronise Last.fm play events using the configured adapters."""

    startup()
    effective_source = source or HttpLastFmPlayEventSource()
    effective_uow = unit_of_work_factory or get_unit_of_work
    service = SyncPlayEvents(source=effective_source, unit_of_work=effective_uow)
    params = request or SyncRequest()

    log.info(
        f"Starting Last.fm sync: batch_size={params.batch_size}, max_events={params.max_events}, "
        f"from={params.from_timestamp}, to={params.to_timestamp}"
    )

    result = service.run(params)

    log.info(
        f"Finished Last.fm sync: stored={result.stored}, fetched={result.fetched}, "
        f"latest={result.latest_timestamp}, now_playing={bool(result.now_playing)}"
    )

    return result


__all__ = ["sync_lastfm_play_events"]
