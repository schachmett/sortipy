from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx
import pytest

from sortipy.adapters.http_resilience import ResilientClient
from sortipy.adapters.lastfm import fetch_play_events
from sortipy.adapters.lastfm.client import (
    LastFmClient,
    parse_play_event,
)
from sortipy.adapters.lastfm.schema import TrackPayload
from sortipy.config import MissingConfigurationError
from sortipy.config.lastfm import (
    LASTFM_BASE_URL,
    LASTFM_TIMEOUT_SECONDS,
    CacheConfig,
    LastFmConfig,
    RateLimit,
    ResilienceConfig,
    get_lastfm_config,
)
from sortipy.domain.model import Provider, User

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sortipy.adapters.lastfm.schema import (
        RecentTracksResponse,
    )


def _make_client_factory(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[[ResilienceConfig], ResilientClient]:
    async def async_handler(request: httpx.Request) -> httpx.Response:
        return handler(request)

    def factory(resilience: ResilienceConfig) -> ResilientClient:
        client = ResilientClient(resilience)
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(async_handler),
        )
        return client

    return factory


def _make_lastfm_config(
    *,
    api_key: str = "demo",
    user_name: str = "demo-user",
) -> LastFmConfig:
    resilience = ResilienceConfig(
        name="lastfm",
        base_url=LASTFM_BASE_URL,
        timeout_seconds=LASTFM_TIMEOUT_SECONDS,
        ratelimit=RateLimit(max_calls=4, per_seconds=1.0),
        cache=CacheConfig(backend="memory"),
    )
    return LastFmConfig(api_key=api_key, user_name=user_name, resilience=resilience)


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


@pytest.fixture
def user() -> User:
    return User(display_name="Listener", lastfm_user="listener")


def test_parse_play_event_creates_canonical_entities(
    sample_payload: dict[str, object],
    user: User,
) -> None:
    event = parse_play_event(sample_payload, user=user)
    validated = TrackPayload.model_validate(sample_payload)

    track = event.track
    assert track is not None
    release = track.release
    release_set = release.release_set
    recording = event.recording
    assert recording.contributions
    artist = recording.contributions[0].artist

    assert event.source is Provider.LASTFM
    assert recording.title == validated.name
    assert release.title == validated.album.title
    assert release_set.title == validated.album.title
    assert artist is not None
    assert artist.name == validated.artist.name
    assert track in release.tracks
    assert release in release_set.releases
    assert track in recording.release_tracks
    assert event.recording is recording
    assert track.provenance is not None
    assert Provider.LASTFM in track.provenance.sources
    assert release.provenance is not None
    assert Provider.LASTFM in release.provenance.sources
    assert recording.provenance is not None
    assert Provider.LASTFM in recording.provenance.sources
    assert release_set.provenance is not None
    assert Provider.LASTFM in release_set.provenance.sources
    assert artist.provenance is not None
    assert Provider.LASTFM in artist.provenance.sources
    assert {eid.namespace for eid in artist.external_ids} == {"musicbrainz:artist", "lastfm:artist"}
    assert {eid.namespace for eid in release_set.external_ids} == {"musicbrainz:release-group"}
    assert {eid.namespace for eid in release.external_ids} == {"musicbrainz:release"}
    assert {eid.namespace for eid in recording.external_ids} == {
        "musicbrainz:recording",
        "lastfm:recording",
    }


def test_parse_play_event_model_creates_domain_model_entities(
    sample_payload: dict[str, object],
    user: User,
) -> None:
    event = parse_play_event(sample_payload, user=user)
    validated = TrackPayload.model_validate(sample_payload)

    track = event.track
    assert track is not None
    release = track.release
    release_set = release.release_set
    recording = event.recording
    user = event.user

    assert event.source is Provider.LASTFM
    assert recording.title == validated.name
    assert release.title == validated.album.title
    assert release_set.title == validated.album.title

    assert event in user.play_events
    assert event.recording is recording

    assert recording.artists
    artist = recording.artists[0]
    assert artist.name == validated.artist.name
    assert release_set.artists
    assert release_set.artists[0] is artist

    assert artist.provenance is not None
    assert Provider.LASTFM in artist.provenance.sources
    assert release_set.provenance is not None
    assert Provider.LASTFM in release_set.provenance.sources
    assert release.provenance is not None
    assert Provider.LASTFM in release.provenance.sources
    assert recording.provenance is not None
    assert Provider.LASTFM in recording.provenance.sources
    assert track.provenance is not None
    assert Provider.LASTFM in track.provenance.sources

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


def test_parse_play_event_without_date_raises(
    sample_payload: dict[str, object],
    user: User,
) -> None:
    payload = sample_payload.copy()
    payload.pop("date", None)

    with pytest.raises(ValueError, match="Invalid scrobble"):
        parse_play_event(payload, user=user)


def test_http_source_fetches_play_events(
    sample_payload: dict[str, object],
    user: User,
) -> None:
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

    config = _make_lastfm_config()
    client = LastFmClient(
        config=config,
        client_factory=_make_client_factory(handler),
    )
    result = fetch_play_events(
        config=config,
        client=client,
        user=user,
        batch_size=5,
        since=datetime.fromtimestamp(1700000000, tz=UTC),
        until=datetime.fromtimestamp(1800000000, tz=UTC),
    )

    events = list(result.events)
    assert len(events) == 1
    event = events[0]
    assert event.source is Provider.LASTFM
    assert result.now_playing is not None


def test_http_source_raises_when_credentials_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    monkeypatch.delenv("LASTFM_USER_NAME", raising=False)

    with pytest.raises(MissingConfigurationError):
        get_lastfm_config()


def test_http_source_raises_when_credentials_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LASTFM_API_KEY", "   ")
    monkeypatch.setenv("LASTFM_USER_NAME", "   ")

    with pytest.raises(MissingConfigurationError):
        get_lastfm_config()


def test_http_source_reads_credentials_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    user: User,
) -> None:
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

    config = get_lastfm_config()
    client = LastFmClient(
        config=config,
        client_factory=_make_client_factory(handler),
    )
    fetch_play_events(config=config, user=user, client=client)

    assert captured["api_key"] == "env-key"
    assert captured["user"] == "env-user"


def test_http_source_handles_multiple_pages_from_recording(
    recent_tracks_payloads: Sequence[RecentTracksResponse],
    user: User,
) -> None:
    responses = recent_tracks_payloads

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        index = min(max(page - 1, 0), len(responses) - 1)
        payload = responses[index]
        return httpx.Response(status_code=200, json=payload.model_dump(by_alias=True))

    config = _make_lastfm_config()
    client = LastFmClient(
        config=config,
        client_factory=_make_client_factory(handler),
    )
    result = fetch_play_events(
        config=config,
        client=client,
        user=user,
        batch_size=5,
        max_events=10,
    )

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
