"""MusicBrainz API client."""

from __future__ import annotations

import asyncio
from logging import getLogger
from typing import TYPE_CHECKING

from sortipy.adapters.http_resilience import ResilientClient

from .schema import MBEntityType, MusicBrainzRecording, MusicBrainzRecordingSearch

if TYPE_CHECKING:
    from collections.abc import Callable

    from sortipy.config.http_resilience import ResilienceConfig
    from sortipy.config.musicbrainz import MusicBrainzConfig

log = getLogger(__name__)

DEFAULT_RECORDING_INC = (
    "artist-credits",
    "isrcs",
    "releases",
    "release-groups",
    "annotation",
    "artist-rels",
    "release-group-rels",
    "url-rels",
)


class MusicBrainzAPIError(RuntimeError):
    """Raised when the MusicBrainz API returns an unexpected response."""


class MusicBrainzClient:
    """Low-level HTTP client for the MusicBrainz API."""

    def __init__(
        self,
        *,
        config: MusicBrainzConfig,
        client_factory: Callable[[ResilienceConfig], ResilientClient] | None = None,
    ) -> None:
        self._config = config
        self._resilience = config.resilience
        self._client_factory = client_factory or ResilientClient

    def fetch_recording(
        self,
        *,
        mbid: str,
        inc: tuple[str, ...] | None = None,
    ) -> MusicBrainzRecording:
        return asyncio.run(self._fetch_recording_async(mbid=mbid, inc=inc))

    def search_recordings(
        self,
        *,
        query: str,
        limit: int = 1,
        offset: int = 0,
        inc: tuple[str, ...] | None = None,
    ) -> MusicBrainzRecordingSearch:
        return asyncio.run(
            self._search_recordings_async(
                query=query,
                limit=limit,
                offset=offset,
                inc=inc,
            )
        )

    def browse_recordings(
        self,
        *,
        artist_mbid: str,
        limit: int = 25,
        offset: int = 0,
        inc: tuple[str, ...] | None = None,
    ) -> MusicBrainzRecordingSearch:
        return asyncio.run(
            self._browse_recordings_async(
                artist_mbid=artist_mbid,
                limit=limit,
                offset=offset,
                inc=inc,
            )
        )

    async def _fetch_recording_async(
        self,
        *,
        mbid: str,
        inc: tuple[str, ...] | None,
    ) -> MusicBrainzRecording:
        inc_values = inc if inc is not None else DEFAULT_RECORDING_INC
        inc_param = "+".join(inc_values) if inc_values else None
        params: dict[str, str] = {"fmt": "json"}
        if inc_param:
            params["inc"] = inc_param

        async with self._client_factory(self._resilience) as client:
            return await self._perform_request(
                client=client,
                path=f"{MBEntityType.RECORDING}/{mbid}",
                params=params,
            )

    async def _search_recordings_async(
        self,
        *,
        query: str,
        limit: int,
        offset: int,
        inc: tuple[str, ...] | None,
    ) -> MusicBrainzRecordingSearch:
        inc_values = inc if inc is not None else DEFAULT_RECORDING_INC
        inc_param = "+".join(inc_values) if inc_values else None
        params: dict[str, str] = {
            "fmt": "json",
            "query": query,
            "limit": str(limit),
            "offset": str(offset),
        }
        if inc_param:
            params["inc"] = inc_param

        async with self._client_factory(self._resilience) as client:
            return await self._perform_search_request(
                client=client,
                path=f"{MBEntityType.RECORDING}",
                params=params,
            )

    async def _browse_recordings_async(
        self,
        *,
        artist_mbid: str,
        limit: int,
        offset: int,
        inc: tuple[str, ...] | None,
    ) -> MusicBrainzRecordingSearch:
        inc_values = inc if inc is not None else DEFAULT_RECORDING_INC
        inc_param = "+".join(inc_values) if inc_values else None
        params: dict[str, str] = {
            "fmt": "json",
            "artist": artist_mbid,
            "limit": str(limit),
            "offset": str(offset),
        }
        if inc_param:
            params["inc"] = inc_param

        async with self._client_factory(self._resilience) as client:
            return await self._perform_search_request(
                client=client,
                path=f"{MBEntityType.RECORDING}",
                params=params,
            )

    async def _perform_request(
        self,
        *,
        client: ResilientClient,
        path: str,
        params: dict[str, str],
    ) -> MusicBrainzRecording:
        base_url = self._resilience.base_url
        if base_url is None:
            raise MusicBrainzAPIError("Missing MusicBrainz base_url in resilience configuration")
        response = await client.get(path, params=params)
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            raise MusicBrainzAPIError("Unexpected MusicBrainz response payload")

        return MusicBrainzRecording.model_validate(payload)

    async def _perform_search_request(
        self,
        *,
        client: ResilientClient,
        path: str,
        params: dict[str, str],
    ) -> MusicBrainzRecordingSearch:
        base_url = self._resilience.base_url
        if base_url is None:
            raise MusicBrainzAPIError("Missing MusicBrainz base_url in resilience configuration")
        response = await client.get(path, params=params)
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            raise MusicBrainzAPIError("Unexpected MusicBrainz response payload")

        return MusicBrainzRecordingSearch.model_validate(payload)
