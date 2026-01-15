"""Last.fm play-event importer."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from sortipy.common.config import LastFmConfig

from .client import LastFmClient

if TYPE_CHECKING:
    from datetime import datetime

    from sortipy.domain.model import User
    from sortipy.domain.ports.fetching import PlayEventFetchResult


@lru_cache(maxsize=1)
def _get_default_client() -> LastFmClient:
    return LastFmClient(config=LastFmConfig.from_environment())


def fetch_play_events(
    *,
    client: LastFmClient | None = None,
    user: User,
    batch_size: int = 200,
    since: datetime | None = None,
    until: datetime | None = None,
    max_events: int | None = None,
) -> PlayEventFetchResult:
    """Fetch Last.fm play events and translate them into domain entities."""

    active_client = client or _get_default_client()
    return active_client.fetch_play_events(
        user=user,
        batch_size=batch_size,
        since=since,
        until=until,
        max_events=max_events,
    )
