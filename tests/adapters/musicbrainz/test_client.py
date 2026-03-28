from __future__ import annotations

from typing import TYPE_CHECKING, Self, cast

import httpx

from sortipy.adapters.musicbrainz.client import MusicBrainzClient

if TYPE_CHECKING:
    from sortipy.adapters.http_resilience import ResilientClient
    from sortipy.config.http_resilience import ResilienceConfig
    from sortipy.config.musicbrainz import MusicBrainzConfig


class FakeResilientClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
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
            200,
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
