"""Application orchestration entry points."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sortipy.adapters.lastfm import HttpLastFmScrobbleSource
from sortipy.common.unit_of_work import get_unit_of_work, startup
from sortipy.domain.data_integration import (
    LastFmScrobbleSource,
    ScrobbleUnitOfWork,
    SyncRequest,
    SyncScrobbles,
    SyncScrobblesResult,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    UnitOfWorkFactory = Callable[[], ScrobbleUnitOfWork]
else:  # pragma: no cover - runtime placeholder for type checking
    UnitOfWorkFactory = object


def sync_lastfm_scrobbles(
    request: SyncRequest | None = None,
    *,
    source: LastFmScrobbleSource | None = None,
    unit_of_work_factory: UnitOfWorkFactory | None = None,
) -> SyncScrobblesResult:
    """Synchronise Last.fm scrobbles using the configured adapters."""

    startup()
    effective_source = source or HttpLastFmScrobbleSource()
    effective_uow = unit_of_work_factory or get_unit_of_work
    service = SyncScrobbles(source=effective_source, unit_of_work=effective_uow)
    return service.run(request)


__all__ = ["sync_lastfm_scrobbles"]
