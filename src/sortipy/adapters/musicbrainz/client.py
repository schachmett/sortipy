"""MusicBrainz API client."""

from __future__ import annotations

import asyncio
from logging import getLogger
from typing import TYPE_CHECKING, Protocol

from sortipy.adapters.http_resilience import ResilientClient

from .schema import MBEntityType, MBRecording, MBRecordingSearch, MBRelease, MBReleaseSearch

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

DEFAULT_RELEASE_INC = ("artists", "recordings", "release-groups", "labels", "url-rels", "aliases")


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
    ) -> MBRecording:
        return asyncio.run(self._fetch_recording_async(mbid=mbid, inc=inc))

    def search_recordings(
        self,
        *,
        query: str,
        limit: int = 1,
        offset: int = 0,
        inc: tuple[str, ...] | None = None,
    ) -> MBRecordingSearch:
        return asyncio.run(
            self._search_recordings_async(
                query=query,
                limit=limit,
                offset=offset,
                inc=inc,
            )
        )

    def fetch_release(
        self,
        *,
        mbid: str,
        inc: tuple[str, ...] | None = None,
    ) -> MBRelease:
        return asyncio.run(self._fetch_release_async(mbid=mbid, inc=inc))

    def search_releases(
        self,
        *,
        query: str,
        limit: int = 10,
        offset: int = 0,
        inc: tuple[str, ...] | None = None,
    ) -> MBReleaseSearch:
        return asyncio.run(
            self._search_releases_async(
                query=query,
                limit=limit,
                offset=offset,
                inc=inc,
            )
        )

    def browse_releases_by_release_group(
        self,
        *,
        release_group_mbid: str,
        limit: int = 25,
        offset: int = 0,
        inc: tuple[str, ...] | None = None,
    ) -> MBReleaseSearch:
        return asyncio.run(
            self._browse_releases_async(
                release_group_mbid=release_group_mbid,
                limit=limit,
                offset=offset,
                inc=inc,
            )
        )

    def browse_releases_by_artist(
        self,
        *,
        artist_mbid: str,
        limit: int = 25,
        offset: int = 0,
        inc: tuple[str, ...] | None = None,
    ) -> MBReleaseSearch:
        return asyncio.run(
            self._browse_releases_async(
                artist_mbid=artist_mbid,
                limit=limit,
                offset=offset,
                inc=inc,
            )
        )

    def browse_recordings_by_artist(
        self,
        *,
        artist_mbid: str,
        limit: int = 25,
        offset: int = 0,
        inc: tuple[str, ...] | None = None,
    ) -> MBRecordingSearch:
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
    ) -> MBRecording:
        inc_values = inc if inc is not None else DEFAULT_RECORDING_INC
        inc_param = "+".join(inc_values) if inc_values else None
        params: dict[str, str] = {"fmt": "json"}
        if inc_param:
            params["inc"] = inc_param

        async with self._client_factory(self._resilience) as client:
            return await self._perform_recording_request(
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
    ) -> MBRecordingSearch:
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
            return await self._perform_recording_search_request(
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
    ) -> MBRecordingSearch:
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
            return await self._perform_recording_search_request(
                client=client,
                path=f"{MBEntityType.RECORDING}",
                params=params,
            )

    async def _fetch_release_async(
        self,
        *,
        mbid: str,
        inc: tuple[str, ...] | None,
    ) -> MBRelease:
        inc_values = inc if inc is not None else DEFAULT_RELEASE_INC
        inc_param = "+".join(inc_values) if inc_values else None
        params: dict[str, str] = {"fmt": "json"}
        if inc_param:
            params["inc"] = inc_param

        async with self._client_factory(self._resilience) as client:
            return await self._perform_release_request(
                client=client,
                path=f"{MBEntityType.RELEASE}/{mbid}",
                params=params,
            )

    async def _search_releases_async(
        self,
        *,
        query: str,
        limit: int,
        offset: int,
        inc: tuple[str, ...] | None,
    ) -> MBReleaseSearch:
        inc_values = inc if inc is not None else DEFAULT_RELEASE_INC
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
            return await self._perform_release_search_request(
                client=client,
                path=f"{MBEntityType.RELEASE}",
                params=params,
            )

    async def _browse_releases_async(
        self,
        *,
        release_group_mbid: str | None = None,
        artist_mbid: str | None = None,
        limit: int,
        offset: int,
        inc: tuple[str, ...] | None,
    ) -> MBReleaseSearch:
        inc_values = inc if inc is not None else DEFAULT_RELEASE_INC
        inc_param = "+".join(inc_values) if inc_values else None
        params: dict[str, str] = {
            "fmt": "json",
            "limit": str(limit),
            "offset": str(offset),
        }
        if release_group_mbid is not None:
            params["release-group"] = release_group_mbid
        if artist_mbid is not None:
            params["artist"] = artist_mbid
        if inc_param:
            params["inc"] = inc_param

        async with self._client_factory(self._resilience) as client:
            return await self._perform_release_search_request(
                client=client,
                path=f"{MBEntityType.RELEASE}",
                params=params,
            )

    async def _perform_recording_request(
        self,
        *,
        client: ResilientClient,
        path: str,
        params: dict[str, str],
    ) -> MBRecording:
        base_url = self._resilience.base_url
        if base_url is None:
            raise MusicBrainzAPIError("Missing MusicBrainz base_url in resilience configuration")
        response = await client.get(path, params=params)
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            raise MusicBrainzAPIError("Unexpected MusicBrainz response payload")

        return MBRecording.model_validate(payload)

    async def _perform_recording_search_request(
        self,
        *,
        client: ResilientClient,
        path: str,
        params: dict[str, str],
    ) -> MBRecordingSearch:
        base_url = self._resilience.base_url
        if base_url is None:
            raise MusicBrainzAPIError("Missing MusicBrainz base_url in resilience configuration")
        response = await client.get(path, params=params)
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            raise MusicBrainzAPIError("Unexpected MusicBrainz response payload")

        return MBRecordingSearch.model_validate(payload)

    async def _perform_release_request(
        self,
        *,
        client: ResilientClient,
        path: str,
        params: dict[str, str],
    ) -> MBRelease:
        base_url = self._resilience.base_url
        if base_url is None:
            raise MusicBrainzAPIError("Missing MusicBrainz base_url in resilience configuration")
        response = await client.get(path, params=params)
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            raise MusicBrainzAPIError("Unexpected MusicBrainz response payload")

        return MBRelease.model_validate(payload)

    async def _perform_release_search_request(
        self,
        *,
        client: ResilientClient,
        path: str,
        params: dict[str, str],
    ) -> MBReleaseSearch:
        base_url = self._resilience.base_url
        if base_url is None:
            raise MusicBrainzAPIError("Missing MusicBrainz base_url in resilience configuration")
        response = await client.get(path, params=params)
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            raise MusicBrainzAPIError("Unexpected MusicBrainz response payload")

        return MBReleaseSearch.model_validate(payload)


class MusicBrainzLookupClient(Protocol):
    def fetch_recording(self, *, mbid: str, inc: tuple[str, ...] | None = None) -> MBRecording: ...

    def search_recordings(
        self,
        *,
        query: str,
        limit: int = 1,
        offset: int = 0,
        inc: tuple[str, ...] | None = None,
    ) -> MBRecordingSearch: ...

    def fetch_release(self, *, mbid: str, inc: tuple[str, ...] | None = None) -> MBRelease: ...

    def browse_releases_by_release_group(
        self,
        *,
        release_group_mbid: str,
        limit: int = 25,
        offset: int = 0,
        inc: tuple[str, ...] | None = None,
    ) -> MBReleaseSearch: ...

    def browse_releases_by_artist(
        self,
        *,
        artist_mbid: str,
        limit: int = 25,
        offset: int = 0,
        inc: tuple[str, ...] | None = None,
    ) -> MBReleaseSearch: ...
