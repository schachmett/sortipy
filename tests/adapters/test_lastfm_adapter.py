from __future__ import annotations

import math
from collections.abc import Sequence  # noqa: TC003
from datetime import UTC, datetime

import httpx
import pytest

from sortipy.adapters.lastfm import (
    CacheConfiguration,
    HttpLastFmScrobbleSource,
    LastFmAPIError,
    LastFmRuntimeOptions,
    RecentTracksResponse,
    RetryConfiguration,
    TrackPayload,
    parse_scrobble,
)
from sortipy.common.config import MissingConfigurationError
from sortipy.domain.data_integration import FetchScrobblesResult
from sortipy.domain.types import Provider


@pytest.fixture
def sample_payload() -> TrackPayload:
    return {
        "artist": {"mbid": "artist-mbid", "#text": "Sample Artist"},
        "streamable": "0",
        "image": [],
        "mbid": "track-mbid",
        "album": {"mbid": "album-mbid", "#text": "Sample Album"},
        "name": "Sample Track",
        "url": "https://last.fm/track",
        "date": {
            "uts": str(int(datetime(2024, 1, 7, 12, tzinfo=UTC).timestamp())),
            "#text": "07 Jan 2024, 12:00",
        },
    }


def test_parse_scrobble_creates_canonical_entities(sample_payload: TrackPayload) -> None:
    scrobble = parse_scrobble(sample_payload)

    track = scrobble.track
    album = track.album
    artist = track.artist

    assert scrobble.provider is Provider.LASTFM
    assert track.name == sample_payload["name"]
    assert album.name == sample_payload["album"]["#text"]
    assert artist.name == sample_payload["artist"]["#text"]
    assert track in album.tracks
    assert album in artist.albums
    assert track in artist.tracks
    assert scrobble in track.scrobbles
    assert Provider.LASTFM in track.sources
    assert Provider.LASTFM in album.sources
    assert Provider.LASTFM in artist.sources


def test_parse_scrobble_without_date_raises(sample_payload: TrackPayload) -> None:
    payload = sample_payload.copy()
    payload.pop("date")

    with pytest.raises(ValueError, match="Invalid scrobble"):
        parse_scrobble(payload)


def test_http_source_fetches_scrobbles(sample_payload: TrackPayload) -> None:
    payload = sample_payload.copy()
    now_playing_payload = sample_payload.copy()
    now_playing_payload.pop("date")
    now_playing_payload["@attr"] = {"nowplaying": "true"}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["user"] == "demo-user"
        assert request.url.params["limit"] == "5"
        return httpx.Response(
            status_code=200,
            json={
                "recenttracks": {
                    "track": [now_playing_payload, payload],
                    "@attr": {
                        "user": "demo-user",
                        "page": "1",
                        "perPage": "5",
                        "total": "1",
                        "totalPages": "1",
                    },
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        source = HttpLastFmScrobbleSource(api_key="demo", user_name="demo-user", client=client)
        result = source.fetch_recent(limit=5, extended=True, from_ts=1700000000, to_ts=1800000000)
    finally:
        client.close()

    assert isinstance(result, FetchScrobblesResult)
    scrobbles = list(result.scrobbles)
    assert len(scrobbles) == 1
    scrobble = scrobbles[0]
    assert scrobble.provider is Provider.LASTFM
    assert result.now_playing is not None


def test_http_source_raises_when_credentials_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    monkeypatch.delenv("LASTFM_USER_NAME", raising=False)

    with pytest.raises(MissingConfigurationError):
        HttpLastFmScrobbleSource()


def test_http_source_raises_when_credentials_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LASTFM_API_KEY", "   ")
    monkeypatch.setenv("LASTFM_USER_NAME", "   ")

    with pytest.raises(MissingConfigurationError):
        HttpLastFmScrobbleSource()


def test_http_source_reads_credentials_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LASTFM_API_KEY", "env-key")
    monkeypatch.setenv("LASTFM_USER_NAME", "env-user")

    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["api_key"] = request.url.params["api_key"]
        captured["user"] = request.url.params["user"]
        return httpx.Response(
            status_code=200,
            json={
                "recenttracks": {
                    "track": [],
                    "@attr": {
                        "user": request.url.params["user"],
                        "page": "1",
                        "perPage": request.url.params.get("limit", "200"),
                        "total": "0",
                        "totalPages": "1",
                    },
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        source = HttpLastFmScrobbleSource(client=client)
        source.fetch_recent()
    finally:
        client.close()

    assert captured["api_key"] == "env-key"
    assert captured["user"] == "env-user"


def test_http_source_handles_multiple_pages_from_recording(
    recent_tracks_payloads: Sequence[RecentTracksResponse],
) -> None:
    responses = recent_tracks_payloads

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        index = min(max(page - 1, 0), len(responses) - 1)
        payload = responses[index]
        return httpx.Response(status_code=200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        source = HttpLastFmScrobbleSource(api_key="demo", user_name="demo-user", client=client)
        first_page = source.fetch_recent(page=1)
        second_page = source.fetch_recent(page=2)
    finally:
        client.close()

    expected_first_page = int(responses[0]["recenttracks"]["@attr"]["page"])
    assert first_page.page == expected_first_page
    assert first_page.total_pages >= first_page.page
    assert first_page.now_playing is None
    first_page_names = [scrobble.track.name for scrobble in first_page.scrobbles]
    assert first_page_names == _extract_names(responses[0])

    expected_second_page = int(responses[1]["recenttracks"]["@attr"]["page"])
    assert second_page.page == expected_second_page
    assert second_page.total_pages >= second_page.page
    assert second_page.now_playing is None
    second_page_names = [scrobble.track.name for scrobble in second_page.scrobbles]
    assert second_page_names == _extract_names(responses[1])


def test_http_source_retries_on_rate_limit_status(sample_payload: TrackPayload) -> None:
    payload_copy = sample_payload.copy()
    attempts = 0
    responses = [
        httpx.Response(status_code=429, headers={"Retry-After": "2"}),
        httpx.Response(status_code=503),
        httpx.Response(status_code=200, json=_make_recenttracks_response([payload_copy])),
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        index = min(attempts, len(responses) - 1)
        attempts += 1
        return responses[index]

    sleep_calls: list[float] = []

    def fake_sleep(duration: float) -> None:
        sleep_calls.append(duration)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        source = HttpLastFmScrobbleSource(
            api_key="demo",
            user_name="demo-user",
            client=client,
            options=LastFmRuntimeOptions(
                retry=RetryConfiguration(max_attempts=4, backoff_initial=0.1),
                sleep=fake_sleep,
            ),
        )
        result = source.fetch_recent(limit=1)
    finally:
        client.close()

    assert attempts == 3
    assert len(sleep_calls) == 2
    assert math.isclose(sleep_calls[0], 2.0, rel_tol=1e-6)
    assert math.isclose(sleep_calls[1], 0.2, rel_tol=1e-6)
    assert [scrobble.track.name for scrobble in result.scrobbles] == [payload_copy["name"]]


def test_http_source_retries_on_rate_limit_error_payload(sample_payload: TrackPayload) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(status_code=200, json={"error": 29, "message": "Rate limit"})
        return httpx.Response(status_code=200, json=_make_recenttracks_response([sample_payload]))

    sleep_calls: list[float] = []

    def fake_sleep(duration: float) -> None:
        sleep_calls.append(duration)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        source = HttpLastFmScrobbleSource(
            api_key="demo",
            user_name="demo-user",
            client=client,
            options=LastFmRuntimeOptions(
                retry=RetryConfiguration(max_attempts=3, backoff_initial=0.2),
                sleep=fake_sleep,
            ),
        )
        result = source.fetch_recent(limit=1)
    finally:
        client.close()

    assert attempts == 2
    assert len(sleep_calls) == 1
    assert math.isclose(sleep_calls[0], 0.2, rel_tol=1e-6)
    scrobbles = list(result.scrobbles)
    assert len(scrobbles) == 1


def test_http_source_raises_on_non_retryable_error() -> None:
    sleep_calls: list[float] = []

    def fake_sleep(duration: float) -> None:
        sleep_calls.append(duration)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json={"error": 6, "message": "Invalid user"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        source = HttpLastFmScrobbleSource(
            api_key="demo",
            user_name="demo-user",
            client=client,
            options=LastFmRuntimeOptions(
                retry=RetryConfiguration(max_attempts=2, backoff_initial=0.1),
                sleep=fake_sleep,
            ),
        )
        with pytest.raises(LastFmAPIError) as exc_info:
            source.fetch_recent()
    finally:
        client.close()

    assert exc_info.value.code == 6
    assert sleep_calls == []


def test_http_source_reuses_cached_response(sample_payload: TrackPayload) -> None:
    payload_copy = sample_payload.copy()
    call_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            status_code=200,
            json=_make_recenttracks_response([payload_copy], page=2, total_pages=5),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        source = HttpLastFmScrobbleSource(
            api_key="demo",
            user_name="demo-user",
            client=client,
            options=LastFmRuntimeOptions(
                cache=CacheConfiguration(ttl_seconds=60.0, max_entries=16),
            ),
        )
        first = source.fetch_recent(page=2, limit=1)
        second = source.fetch_recent(page=2, limit=1)
    finally:
        client.close()

    assert call_count == 1
    assert [s.track.name for s in first.scrobbles] == [payload_copy["name"]]
    assert [s.track.name for s in second.scrobbles] == [payload_copy["name"]]


def test_http_source_cache_expires_after_ttl(sample_payload: TrackPayload) -> None:
    class FakeClock:
        def __init__(self) -> None:
            self.value = 0.0

        def time(self) -> float:
            return self.value

        def advance(self, amount: float) -> None:
            self.value += amount

    clock = FakeClock()
    attempts = 0

    first_payload = sample_payload.copy()
    second_payload = sample_payload.copy()
    second_payload["name"] = "Updated Track"

    responses = [
        _make_recenttracks_response([first_payload]),
        _make_recenttracks_response([second_payload]),
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        index = min(attempts, len(responses) - 1)
        attempts += 1
        return httpx.Response(status_code=200, json=responses[index])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        source = HttpLastFmScrobbleSource(
            api_key="demo",
            user_name="demo-user",
            client=client,
            options=LastFmRuntimeOptions(
                cache=CacheConfiguration(ttl_seconds=5.0, max_entries=4),
                time_provider=clock.time,
            ),
        )
        first = source.fetch_recent(limit=1)
        clock.advance(1.0)
        cached = source.fetch_recent(limit=1)
        clock.advance(10.0)
        refreshed = source.fetch_recent(limit=1)
    finally:
        client.close()

    assert attempts == 2
    first_names = [s.track.name for s in first.scrobbles]
    cached_names = [s.track.name for s in cached.scrobbles]
    refreshed_names = [s.track.name for s in refreshed.scrobbles]
    assert first_names == cached_names
    assert refreshed_names != first_names


def test_http_source_does_not_cache_now_playing(sample_payload: TrackPayload) -> None:
    now_playing_payload = sample_payload.copy()
    now_playing_payload.pop("date", None)
    now_playing_payload["@attr"] = {"nowplaying": "true"}

    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            status_code=200,
            json=_make_recenttracks_response([now_playing_payload, sample_payload]),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        source = HttpLastFmScrobbleSource(
            api_key="demo",
            user_name="demo-user",
            client=client,
            options=LastFmRuntimeOptions(
                cache=CacheConfiguration(ttl_seconds=60.0, max_entries=16),
            ),
        )
        first = source.fetch_recent(page=1, limit=2)
        second = source.fetch_recent(page=1, limit=2)
    finally:
        client.close()

    assert attempts == 2
    assert first.now_playing is not None
    assert second.now_playing is not None


def _make_recenttracks_response(
    payloads: Sequence[TrackPayload],
    *,
    page: int = 1,
    total_pages: int = 1,
) -> RecentTracksResponse:
    return {
        "recenttracks": {
            "track": list(payloads),
            "@attr": {
                "user": "demo-user",
                "page": str(page),
                "perPage": str(len(payloads)),
                "total": str(len(payloads)),
                "totalPages": str(total_pages),
            },
        }
    }


def _extract_names(payload: RecentTracksResponse) -> list[str]:
    return [item["name"] for item in payload["recenttracks"]["track"] if "date" in item]
