from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from sortipy.adapters.lastfm import HttpLastFmScrobbleSource, TrackPayload, parse_scrobble
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


def test_http_source_handles_multiple_pages_from_recording() -> None:
    responses = _load_fixture_pages()

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        payload = responses[page]
        return httpx.Response(status_code=200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        source = HttpLastFmScrobbleSource(api_key="demo", user_name="demo-user", client=client)
        first_page = source.fetch_recent(page=1)
        second_page = source.fetch_recent(page=2)
    finally:
        client.close()

    assert first_page.page == 1
    assert first_page.total_pages == 2
    assert first_page.now_playing is not None
    assert [scrobble.track.name for scrobble in first_page.scrobbles] == ["Log Song"]

    assert second_page.page == 2
    assert second_page.total_pages == 2
    assert second_page.now_playing is None
    assert [scrobble.track.name for scrobble in second_page.scrobbles] == ["Historical Track"]


def _load_fixture_pages() -> dict[int, dict[str, Any]]:
    path = Path(__file__).resolve().parent.parent / "data" / "lastfm_recent_tracks.jsonl"
    mapping: dict[int, dict[str, Any]] = {}
    with path.open() as handle:
        for line in handle:
            payload = json.loads(line)
            page = int(payload["recenttracks"]["@attr"]["page"])
            mapping[page] = payload
    return mapping
