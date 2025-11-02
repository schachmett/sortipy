"""Fetch data from Last.fm API."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from logging import getLogger
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict, cast

import httpx

from sortipy.adapters.http_resilience import (
    CacheConfig,
    RateLimit,
    ResilienceConfig,
    ResilientClient,
)
from sortipy.common.config import LastFmConfig
from sortipy.domain.ports.fetching import PlayEventFetcher, PlayEventFetchResult
from sortipy.domain.types import (
    Artist,
    ArtistRole,
    ExternalNamespace,
    PlayEvent,
    Provider,
    Recording,
    RecordingArtist,
    Release,
    ReleaseSet,
    ReleaseSetArtist,
    Track,
)

log = getLogger(__name__)


LASTFM_BASE_URL = "https://ws.audioscrobbler.com/2.0/"
_DEFAULT_TIMEOUT_SECONDS = 10.0


def _datetime_to_epoch_seconds(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.astimezone(UTC).timestamp())


### Last.fm schema definition ###


type ImageSize = Literal["small", "medium", "large", "extralarge"]
ArtistPayload = TypedDict("ArtistPayload", {"mbid": str, "#text": str})
Image = TypedDict("Image", {"size": ImageSize, "#text": str})
AlbumPayload = TypedDict("AlbumPayload", {"mbid": str, "#text": str})
Date = TypedDict("Date", {"uts": str, "#text": str})


class TrackAttr(TypedDict):
    nowplaying: Literal["true"]


TrackPayload = TypedDict(
    "TrackPayload",
    {
        "artist": ArtistPayload,
        "streamable": Literal["0", "1"],
        "image": list[Image],
        "mbid": str,
        "album": AlbumPayload,
        "name": str,
        "url": str,
        "date": NotRequired[Date],
        "@attr": NotRequired[TrackAttr],
    },
)


class ResponseAttr(TypedDict):
    user: str
    totalPages: str
    page: str
    perPage: str
    total: str


RecentTracks = TypedDict("RecentTracks", {"track": list[TrackPayload], "@attr": ResponseAttr})


class RecentTracksResponse(TypedDict):
    recenttracks: RecentTracks


class LastFmErrorResponse(TypedDict, total=False):
    error: int
    message: str


### resilient adapter config ###


def _should_cache_payload(payload: object) -> bool:
    recenttracks_payload = cast(RecentTracksResponse, payload)
    return not any(
        track.get("@attr", {}).get("nowplaying") == "true"
        for track in recenttracks_payload["recenttracks"]["track"]
    )


def _default_resilience_config() -> ResilienceConfig:
    return ResilienceConfig(
        name="lastfm",
        base_url=LASTFM_BASE_URL,
        timeout_seconds=_DEFAULT_TIMEOUT_SECONDS,
        ratelimit=RateLimit(max_calls=4, per_seconds=1.0),
        cache=CacheConfig(backend="memory", should_cache=_should_cache_payload),
    )


def _default_client_factory(config: ResilienceConfig) -> ResilientClient:
    return ResilientClient(config)


### actual adapter ###


class LastFmAPIError(RuntimeError):
    """Raised when the Last.fm API returns an application-level error."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(slots=True)
class LastFmFetcher:
    config: LastFmConfig = field(default_factory=LastFmConfig.from_environment)
    resilience: ResilienceConfig = field(default_factory=_default_resilience_config)
    client_factory: Callable[[ResilienceConfig], ResilientClient] = field(
        default=_default_client_factory
    )

    def __call__(
        self,
        *,
        batch_size: int = 200,
        since: datetime | None = None,
        until: datetime | None = None,
        max_events: int | None = None,
    ) -> PlayEventFetchResult:
        return asyncio.run(
            self._fetch_play_events_async(
                batch_size=batch_size,
                since=since,
                until=until,
                max_events=max_events,
            )
        )

    async def _fetch_play_events_async(
        self,
        *,
        batch_size: int,
        since: datetime | None,
        until: datetime | None,
        max_events: int | None,
    ) -> PlayEventFetchResult:
        from_ts = _datetime_to_epoch_seconds(since) + 1 if since else None
        to_ts = _datetime_to_epoch_seconds(until) if until else None

        events: list[PlayEvent] = []
        now_playing: PlayEvent | None = None
        page = 1
        remaining = max_events

        async with self.client_factory(self.resilience) as client:
            while True:
                track_payloads, attrs = await self._request_recent_scrobbles(
                    client=client,
                    page=page,
                    limit=batch_size,
                    from_ts=from_ts,
                    to_ts=to_ts,
                    extended=True,
                )

                for track_payload in track_payloads:
                    if track_payload.get("@attr", {}).get("nowplaying") == "true":
                        now_playing = parse_play_event(track_payload)
                        continue
                    event = parse_play_event(track_payload)
                    events.append(event)
                    if remaining is not None:
                        remaining -= 1
                        if remaining <= 0:
                            return PlayEventFetchResult(events=events, now_playing=now_playing)

                total_pages = int(attrs["totalPages"])
                if page >= total_pages:
                    break
                page += 1
                from_ts = None

        return PlayEventFetchResult(events=events, now_playing=now_playing)

    async def _request_recent_scrobbles(
        self,
        *,
        client: ResilientClient,
        page: int,
        limit: int,
        from_ts: int | None,
        to_ts: int | None,
        extended: bool,
    ) -> tuple[list[TrackPayload], ResponseAttr]:
        params: dict[str, str | int] = {
            "method": "user.getrecenttracks",
            "user": self.config.user_name,
            "limit": limit,
            "page": page,
            "api_key": self.config.api_key,
            "format": "json",
        }
        if from_ts is not None:
            params["from"] = from_ts
        if to_ts is not None:
            params["to"] = to_ts
        if extended:
            params["extended"] = 1

        query_params = httpx.QueryParams(params)
        response_json = await self._perform_request(client=client, params=query_params)
        recent = response_json["recenttracks"]
        return recent["track"], recent["@attr"]

    async def _perform_request(
        self,
        *,
        client: ResilientClient,
        params: httpx.QueryParams,
    ) -> RecentTracksResponse:
        base_url = self.resilience.base_url or LASTFM_BASE_URL
        response = await client.get(base_url, params=params)
        response.raise_for_status()

        payload = response.json()
        if isinstance(payload, dict) and "error" in payload:
            error_payload = cast(LastFmErrorResponse, payload)
            error_code = error_payload.get("error")
            message = error_payload.get("message", "Last.fm API error")
            detail = f"{error_code}: {message}" if isinstance(error_code, int) else message
            log.error("Last.fm API error %s", detail)
            raise LastFmAPIError(
                message,
                code=error_code if isinstance(error_code, int) else None,
            ) from None

        if not isinstance(payload, dict) or "recenttracks" not in payload:
            raise LastFmAPIError("Unexpected Last.fm response payload")

        return cast(RecentTracksResponse, payload)


if TYPE_CHECKING:
    from collections.abc import Callable

    _fetcher_check: PlayEventFetcher = LastFmFetcher()


def parse_play_event(scrobble: TrackPayload) -> PlayEvent:
    if "@attr" in scrobble and scrobble["@attr"].get("nowplaying") == "true":
        played_at = datetime.now(UTC)
    elif "date" in scrobble:
        played_at = datetime.fromtimestamp(int(scrobble["date"]["uts"]), tz=UTC)
    else:
        raise ValueError("Invalid scrobble")

    try:
        artist, release_set, _release, recording, track = _parse_entities(scrobble)
    except Exception:  # pragma: no cover - defensive logging
        log.exception("Error parsing play event")
        raise

    event = PlayEvent(
        played_at=played_at,
        source=Provider.LASTFM,
        recording=recording,
        track=track,
    )
    recording.play_events.append(event)
    track.play_events.append(event)

    if recording not in artist.recordings:
        artist.recordings.append(recording)
    if release_set not in artist.release_sets:
        artist.release_sets.append(release_set)

    return event


def _parse_entities(payload: TrackPayload) -> tuple[Artist, ReleaseSet, Release, Recording, Track]:
    artist_name = payload["artist"]["#text"]
    artist_mbid = payload["artist"]["mbid"] or None
    artist = Artist(name=artist_name)
    if artist_mbid:
        artist.add_external_id(ExternalNamespace.MUSICBRAINZ_ARTIST, artist_mbid)
    artist.sources.add(Provider.LASTFM)

    album_name = payload["album"]["#text"]
    album_mbid = payload["album"]["mbid"] or None
    release_set = ReleaseSet(title=album_name)
    release_set.sources.add(Provider.LASTFM)
    if album_mbid:
        release_set.add_external_id(ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP, album_mbid)

    release = Release(title=album_name or payload["name"], release_set=release_set)
    release.sources.add(Provider.LASTFM)
    if album_mbid:
        release.add_external_id(ExternalNamespace.MUSICBRAINZ_RELEASE, album_mbid)

    track_mbid = payload.get("mbid") or None
    recording = Recording(title=payload["name"])
    recording.sources.add(Provider.LASTFM)
    if track_mbid:
        recording.add_external_id(ExternalNamespace.MUSICBRAINZ_RECORDING, track_mbid)

    track = Track(
        release=release,
        recording=recording,
    )
    track.sources.add(Provider.LASTFM)

    release_set.releases.append(release)
    release_set.artists.append(
        ReleaseSetArtist(
            release_set=release_set,
            artist=artist,
            role=ArtistRole.PRIMARY,
        )
    )

    release.tracks.append(track)

    recording.tracks.append(track)
    recording.artists.append(
        RecordingArtist(recording=recording, artist=artist, role=ArtistRole.PRIMARY)
    )

    return artist, release_set, release, recording, track
