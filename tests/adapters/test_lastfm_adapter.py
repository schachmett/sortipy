from __future__ import annotations

import math
from collections.abc import Sequence  # noqa: TC003
from datetime import UTC, datetime

import httpx
import pytest

from sortipy.adapters.lastfm import (
    CacheConfiguration,
    LastFmRuntimeOptions,
    RecentTracksResponse,
    RetryConfiguration,
    TrackPayload,
    build_http_lastfm_fetcher,
    parse_play_event,
)
from sortipy.common.config import ConfigurationError, MissingConfigurationError
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


def test_parse_play_event_creates_canonical_entities(sample_payload: TrackPayload) -> None:
    event = parse_play_event(sample_payload)

    track = event.track
    assert track is not None
    release = track.release
    release_set = release.release_set
    recording = event.recording
    assert recording.artists
    artist = recording.artists[0].artist

    assert event.source is Provider.LASTFM
    assert recording.title == sample_payload["name"]
    assert release.title == sample_payload["album"]["#text"]
    assert release_set.title == sample_payload["album"]["#text"]
    assert artist is not None
    assert artist.name == sample_payload["artist"]["#text"]
    assert track in release.tracks
    assert release in release_set.releases
    assert track in recording.tracks
    assert event in track.play_events
    assert event in recording.play_events
    assert Provider.LASTFM in track.sources
    assert Provider.LASTFM in release.sources
    assert Provider.LASTFM in recording.sources
    assert Provider.LASTFM in release_set.sources
    assert Provider.LASTFM in artist.sources
    assert {eid.namespace for eid in artist.external_ids} == {"musicbrainz:artist"}
    assert {eid.namespace for eid in release_set.external_ids} == {"musicbrainz:release-group"}
    assert {eid.namespace for eid in release.external_ids} == {"musicbrainz:release"}
    assert {eid.namespace for eid in recording.external_ids} == {"musicbrainz:recording"}


def test_parse_play_event_without_date_raises(sample_payload: TrackPayload) -> None:
    payload = sample_payload.copy()
    payload.pop("date")

    with pytest.raises(ValueError, match="Invalid scrobble"):
        parse_play_event(payload)


def test_http_source_fetches_play_events(sample_payload: TrackPayload) -> None:
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
    fetcher = build_http_lastfm_fetcher(
        api_key="demo",
        user_name="demo-user",
        client=client,
    )
    result = fetcher(
        batch_size=5,
        since=datetime.fromtimestamp(1700000000, tz=UTC),
        until=datetime.fromtimestamp(1800000000, tz=UTC),
    )
    client.close()

    events = list(result.events)
    assert len(events) == 1
    event = events[0]
    assert event.source is Provider.LASTFM
    assert result.now_playing is not None


def test_http_source_raises_when_credentials_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    monkeypatch.delenv("LASTFM_USER_NAME", raising=False)

    with pytest.raises(MissingConfigurationError):
        build_http_lastfm_fetcher()


def test_http_source_raises_when_credentials_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LASTFM_API_KEY", "   ")
    monkeypatch.setenv("LASTFM_USER_NAME", "   ")

    with pytest.raises(MissingConfigurationError):
        build_http_lastfm_fetcher()


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
    fetcher = build_http_lastfm_fetcher(client=client)
    fetcher()
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
    fetcher = build_http_lastfm_fetcher(
        api_key="demo",
        user_name="demo-user",
        client=client,
    )
    result = fetcher(batch_size=5, max_events=10)
    client.close()

    names = [event.recording.title for event in result.events]
    expected_names: list[str] = []
    for payload in responses:
        expected_names.extend(_extract_names(payload))
        if len(expected_names) >= 10:
            break
    expected_names = expected_names[:10]
    assert names == expected_names


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
    fetcher = build_http_lastfm_fetcher(
        api_key="demo",
        user_name="demo-user",
        client=client,
        options=LastFmRuntimeOptions(
            retry=RetryConfiguration(max_attempts=4, backoff_initial=0.1),
            sleep=fake_sleep,
        ),
    )
    result = fetcher(batch_size=1)
    client.close()

    assert attempts == 3
    assert len(sleep_calls) == 2
    assert math.isclose(sleep_calls[0], 2.0, rel_tol=1e-6)
    assert math.isclose(sleep_calls[1], 0.2, rel_tol=1e-6)
    assert [event.recording.title for event in result.events] == [payload_copy["name"]]


def test_http_source_retries_on_consecutive_rate_limit_errors(
    sample_payload: TrackPayload,
) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(status_code=200, json={"error": 29, "message": "Rate limit"})
        return httpx.Response(status_code=200, json=_make_recenttracks_response([sample_payload]))

    sleep_calls: list[float] = []

    def fake_sleep(duration: float) -> None:
        sleep_calls.append(duration)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = build_http_lastfm_fetcher(
        api_key="demo",
        user_name="demo-user",
        client=client,
        options=LastFmRuntimeOptions(
            retry=RetryConfiguration(max_attempts=4, backoff_initial=0.1, backoff_factor=2.0),
            sleep=fake_sleep,
        ),
    )
    result = fetcher(batch_size=1)
    client.close()

    assert attempts == 3
    assert len(sleep_calls) == 2
    assert math.isclose(sleep_calls[0], 0.1, rel_tol=1e-6)
    assert math.isclose(sleep_calls[1], 0.2, rel_tol=1e-6)
    assert [event.recording.title for event in result.events] == [sample_payload["name"]]


def test_retry_configuration_rejects_invalid_values() -> None:
    with pytest.raises(ConfigurationError, match="max_attempts"):
        RetryConfiguration(max_attempts=0)
    with pytest.raises(ConfigurationError, match="backoff_initial"):
        RetryConfiguration(backoff_initial=-1.0)
    with pytest.raises(ConfigurationError, match="backoff_factor"):
        RetryConfiguration(backoff_factor=0.5)
    with pytest.raises(ConfigurationError, match="backoff_max"):
        RetryConfiguration(backoff_initial=2.0, backoff_max=1.0)


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
    fetcher = build_http_lastfm_fetcher(
        api_key="demo",
        user_name="demo-user",
        client=client,
        options=LastFmRuntimeOptions(
            cache=CacheConfiguration(ttl_seconds=60.0, max_entries=16),
        ),
    )
    first = fetcher(batch_size=2)
    second = fetcher(batch_size=2)
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
