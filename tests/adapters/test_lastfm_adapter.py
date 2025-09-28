from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from sortipy.adapters.lastfm import HttpLastFmScrobbleSource, TrackPayload, parse_scrobble
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
