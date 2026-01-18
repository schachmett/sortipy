"""Last.fm play-event importer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .client import LastFmClient

if TYPE_CHECKING:
    from datetime import datetime

    from sortipy.config.lastfm import LastFmConfig
    from sortipy.domain.model import User
    from sortipy.domain.ports.fetching import PlayEventFetchResult


def fetch_play_events(
    *,
    config: LastFmConfig,
    client: LastFmClient | None = None,
    user: User,
    batch_size: int = 200,
    since: datetime | None = None,
    until: datetime | None = None,
    max_events: int | None = None,
) -> PlayEventFetchResult:
    """Fetch Last.fm play events and translate them into domain entities."""

    active_client = client or LastFmClient(config=config)
    return active_client.fetch_play_events(
        user=user,
        batch_size=batch_size,
        since=since,
        until=until,
        max_events=max_events,
    )
