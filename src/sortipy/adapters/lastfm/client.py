"""HTTP client for the Last.fm API."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from logging import getLogger
from typing import TYPE_CHECKING

import httpx

from sortipy.adapters.http_resilience import ResilientClient
from sortipy.domain.ports.fetching import PlayEventFetchResult

from .schema import ErrorResponse, RecentTracksResponse, ResponseAttr, TrackPayload
from .translator import parse_play_event

if TYPE_CHECKING:
    from collections.abc import Callable

    from sortipy.config.http_resilience import ResilienceConfig
    from sortipy.config.lastfm import LastFmConfig
    from sortipy.domain.model import PlayEvent, User

log = getLogger(__name__)


def _datetime_to_epoch_seconds(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.astimezone(UTC).timestamp())


class LastFmAPIError(RuntimeError):
    """Raised when the Last.fm API returns an application-level error."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class LastFmClient:
    """Low-level HTTP client for the Last.fm API."""

    def __init__(
        self,
        *,
        config: LastFmConfig,
        client_factory: Callable[[ResilienceConfig], ResilientClient] | None = None,
    ) -> None:
        self._config = config
        self._resilience = config.resilience
        self._client_factory = client_factory or ResilientClient

    def fetch_play_events(
        self,
        *,
        user: User,
        batch_size: int = 200,
        since: datetime | None = None,
        until: datetime | None = None,
        max_events: int | None = None,
    ) -> PlayEventFetchResult:
        return asyncio.run(
            self._fetch_play_events_async(
                user=user,
                batch_size=batch_size,
                since=since,
                until=until,
                max_events=max_events,
            )
        )

    async def _fetch_play_events_async(
        self,
        *,
        user: User,
        batch_size: int,
        since: datetime | None,
        until: datetime | None,
        max_events: int | None,
    ) -> PlayEventFetchResult:
        from_ts = _datetime_to_epoch_seconds(since) + 1 if since else None
        to_ts = _datetime_to_epoch_seconds(until) if until else None

        events: list[PlayEvent] = []
        now_playing: PlayEvent | None = None
        page = 1
        remaining = max_events

        async with self._client_factory(self._resilience) as client:
            while True:
                track_payloads, attrs = await self._request_recent_scrobbles(
                    client=client,
                    page=page,
                    limit=batch_size,
                    from_ts=from_ts,
                    to_ts=to_ts,
                    extended=True,
                )

                for track_payload in track_payloads:
                    if track_payload.is_now_playing:
                        now_playing = parse_play_event(track_payload, user=user)
                        continue
                    event = parse_play_event(track_payload, user=user)
                    events.append(event)
                    if remaining is not None:
                        remaining -= 1
                        if remaining <= 0:
                            return PlayEventFetchResult(events=events, now_playing=now_playing)

                total_pages = attrs.total_pages
                if page >= total_pages:
                    break
                page += 1
                from_ts = None

        return PlayEventFetchResult(events=events, now_playing=now_playing)

    async def _request_recent_scrobbles(
        self,
        *,
        client: ResilientClient,
        page: int,
        limit: int,
        from_ts: int | None,
        to_ts: int | None,
        extended: bool,
    ) -> tuple[list[TrackPayload], ResponseAttr]:
        params: dict[str, str | int] = {
            "method": "user.getrecenttracks",
            "user": self._config.user_name,
            "limit": limit,
            "page": page,
            "api_key": self._config.api_key,
            "format": "json",
        }
        if from_ts is not None:
            params["from"] = from_ts
        if to_ts is not None:
            params["to"] = to_ts
        if extended:
            params["extended"] = 1

        query_params = httpx.QueryParams(params)
        response_json = await self._perform_request(client=client, params=query_params)
        recent = response_json.recenttracks
        return recent.track, recent.attr

    async def _perform_request(
        self,
        *,
        client: ResilientClient,
        params: httpx.QueryParams,
    ) -> RecentTracksResponse:
        base_url = self._resilience.base_url
        if base_url is None:
            raise LastFmAPIError("Missing Last.fm base_url in resilience configuration")
        response = await client.get(base_url, params=params)
        response.raise_for_status()

        payload = response.json()
        if isinstance(payload, dict) and "error" in payload:
            error_payload = ErrorResponse.model_validate(payload)
            log.error(f"Last.fm API error {error_payload.error}: {error_payload.message}")
            raise LastFmAPIError(error_payload.message, code=error_payload.error) from None

        if not isinstance(payload, dict) or "recenttracks" not in payload:
            raise LastFmAPIError("Unexpected Last.fm response payload")

        return RecentTracksResponse.model_validate(payload)


def should_cache_recent_tracks(payload: object) -> bool:
    """Skip caching responses that contain now-playing items."""

    response = RecentTracksResponse.model_validate(payload)
    return not any(track.is_now_playing for track in response.recenttracks.track)
