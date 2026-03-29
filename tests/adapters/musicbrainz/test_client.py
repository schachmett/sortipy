from __future__ import annotations

from typing import TYPE_CHECKING, Self, cast

import httpx
import pytest

from sortipy.adapters.musicbrainz.client import MusicBrainzClient, MusicBrainzNotFoundError

if TYPE_CHECKING:
    from sortipy.adapters.http_resilience import ResilientClient
    from sortipy.config.http_resilience import ResilienceConfig
    from sortipy.config.musicbrainz import MusicBrainzConfig


class FakeResilientClient:
    def __init__(self, payload: dict[str, object], *, status_code: int = 200) -> None:
        self._payload = payload
        self._status_code = status_code
        self.follow_redirects: list[bool | object] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        _ = (exc_type, exc, tb)

    async def get(
        self,
        url: str,
        *,
        params: dict[str, str],
        follow_redirects: bool | object = False,
    ) -> httpx.Response:
        self.follow_redirects.append(follow_redirects)
        return httpx.Response(
            self._status_code,
            json=self._payload,
            request=httpx.Request("GET", f"http://example.com/{url}", params=params),
        )


def test_musicbrainz_client_follows_redirects_for_release_requests(
    release_payloads_by_id: dict[str, dict[str, object]],
    musicbrainz_config: MusicBrainzConfig,
) -> None:
    mbid, payload = next(iter(release_payloads_by_id.items()))
    fake = FakeResilientClient(payload)

    def _factory(_config: ResilienceConfig) -> ResilientClient:
        return cast("ResilientClient", fake)

    client = MusicBrainzClient(
        config=musicbrainz_config,
        client_factory=_factory,
    )

    release = client.fetch_release(mbid=mbid)

    assert release.id == mbid
    assert fake.follow_redirects == [True]


def test_musicbrainz_client_raises_not_found_error_for_missing_recording(
    musicbrainz_config: MusicBrainzConfig,
) -> None:
    fake = FakeResilientClient({}, status_code=404)

    def _factory(_config: ResilienceConfig) -> ResilientClient:
        return cast("ResilientClient", fake)

    client = MusicBrainzClient(
        config=musicbrainz_config,
        client_factory=_factory,
    )

    with pytest.raises(MusicBrainzNotFoundError) as exc_info:
        client.fetch_recording(mbid="53e28b87-5b7c-4f57-8baa-e9f65023ff9d")

    assert "recording/53e28b87-5b7c-4f57-8baa-e9f65023ff9d" in str(exc_info.value)
