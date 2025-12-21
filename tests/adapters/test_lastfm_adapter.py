from __future__ import annotations

from collections.abc import Callable, Sequence  # noqa: TC003
from datetime import UTC, datetime

import httpx
import pytest

from sortipy.adapters.http_resilience import ResilienceConfig, ResilientClient
from sortipy.adapters.lastfm import (
    LastFmFetcher,
    RecentTracksResponse,
    TrackPayload,
    parse_play_event,
)
from sortipy.adapters.lastfm.translator import parse_play_event_model
from sortipy.common.config import LastFmConfig, MissingConfigurationError
from sortipy.domain.model.enums import Provider as ModelProvider
from sortipy.domain.types import Provider


def _make_client_factory(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[[ResilienceConfig], ResilientClient]:
    async def async_handler(request: httpx.Request) -> httpx.Response:
        return handler(request)

    def factory(resilience: ResilienceConfig) -> ResilientClient:
        client = ResilientClient(resilience)
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(async_handler))  # noqa: SLF001  # type: ignore[reportPrivateUsage]
        return client

    return factory


@pytest.fixture
def sample_payload() -> dict[str, object]:
    return {
        "artist": {
            "mbid": "artist-mbid",
            "#text": "Sample Artist",
            "url": "https://last.fm/artist",
        },
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


def test_parse_play_event_creates_canonical_entities(sample_payload: dict[str, object]) -> None:
    event = parse_play_event(sample_payload)
    validated = TrackPayload.model_validate(sample_payload)

    track = event.track
    assert track is not None
    release = track.release
    release_set = release.release_set
    recording = event.recording
    assert recording.artist_links
    artist = recording.artist_links[0].artist

    assert event.source is Provider.LASTFM
    assert recording.title == validated.name
    assert release.title == validated.album.title
    assert release_set.title == validated.album.title
    assert artist is not None
    assert artist.name == validated.artist.name
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
    assert {eid.namespace for eid in artist.external_ids} == {"musicbrainz:artist", "lastfm:artist"}
    assert {eid.namespace for eid in release_set.external_ids} == {"musicbrainz:release-group"}
    assert {eid.namespace for eid in release.external_ids} == {"musicbrainz:release"}
    assert {eid.namespace for eid in recording.external_ids} == {
        "musicbrainz:recording",
        "lastfm:recording",
    }


def test_parse_play_event_model_creates_domain_model_entities(
    sample_payload: dict[str, object],
) -> None:
    event = parse_play_event_model(sample_payload)
    validated = TrackPayload.model_validate(sample_payload)

    track = event.track
    assert track is not None
    release = track.release
    release_set = release.release_set
    recording = event.recording
    user = event.user

    assert event.source is ModelProvider.LASTFM
    assert recording.title == validated.name
    assert release.title == validated.album.title
    assert release_set.title == validated.album.title

    assert event in user.play_events
    assert event in recording.play_events

    assert recording.artists
    artist = recording.artists[0]
    assert artist.name == validated.artist.name
    assert release_set.artists
    assert release_set.artists[0] is artist

    assert artist.provenance is not None
    assert ModelProvider.LASTFM in artist.provenance.sources
    assert release_set.provenance is not None
    assert ModelProvider.LASTFM in release_set.provenance.sources
    assert release.provenance is not None
    assert ModelProvider.LASTFM in release.provenance.sources
    assert recording.provenance is not None
    assert ModelProvider.LASTFM in recording.provenance.sources
    assert track.provenance is not None
    assert ModelProvider.LASTFM in track.provenance.sources

    assert {str(eid.namespace) for eid in artist.external_ids} == {
        "musicbrainz:artist",
        "lastfm:artist",
    }
    assert {str(eid.namespace) for eid in release_set.external_ids} == {"musicbrainz:release-group"}
    assert {str(eid.namespace) for eid in release.external_ids} == {"musicbrainz:release"}
    assert {str(eid.namespace) for eid in recording.external_ids} == {
        "musicbrainz:recording",
        "lastfm:recording",
    }


def test_parse_play_event_without_date_raises(sample_payload: dict[str, object]) -> None:
    payload = sample_payload.copy()
    payload.pop("date", None)

    with pytest.raises(ValueError, match="Invalid scrobble"):
        parse_play_event(payload)


def test_http_source_fetches_play_events(sample_payload: dict[str, object]) -> None:
    payload = sample_payload.copy()
    now_playing_payload = sample_payload.copy()
    now_playing_payload.pop("date", None)
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

    fetcher = LastFmFetcher(
        config=LastFmConfig(api_key="demo", user_name="demo-user"),
        client_factory=_make_client_factory(handler),
    )
    result = fetcher(
        batch_size=5,
        since=datetime.fromtimestamp(1700000000, tz=UTC),
        until=datetime.fromtimestamp(1800000000, tz=UTC),
    )

    events = list(result.events)
    assert len(events) == 1
    event = events[0]
    assert event.source is Provider.LASTFM
    assert result.now_playing is not None


def test_http_source_raises_when_credentials_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    monkeypatch.delenv("LASTFM_USER_NAME", raising=False)

    with pytest.raises(MissingConfigurationError):
        LastFmFetcher()


def test_http_source_raises_when_credentials_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LASTFM_API_KEY", "   ")
    monkeypatch.setenv("LASTFM_USER_NAME", "   ")

    with pytest.raises(MissingConfigurationError):
        LastFmFetcher()


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

    fetcher = LastFmFetcher(client_factory=_make_client_factory(handler))
    fetcher()

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
        return httpx.Response(status_code=200, json=payload.model_dump(by_alias=True))

    fetcher = LastFmFetcher(
        config=LastFmConfig(api_key="demo", user_name="demo-user"),
        client_factory=_make_client_factory(handler),
    )
    result = fetcher(batch_size=5, max_events=10)

    names = [event.recording.title for event in result.events]
    expected_names: list[str] = []
    for payload in responses:
        expected_names.extend(_extract_names(payload))
        if len(expected_names) >= 10:
            break
    expected_names = expected_names[:10]
    assert names == expected_names


def _extract_names(payload: RecentTracksResponse) -> list[str]:
    return [item.name for item in payload.recenttracks.track if item.date is not None]
