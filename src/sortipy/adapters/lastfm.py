"""Fetch data from Last.fm API."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from logging import getLogger
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict, cast

import httpx

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
else:  # pragma: no cover - imported for runtime type hint resolution
    from collections.abc import Callable as _Callable
    from collections.abc import Mapping as _Mapping

    Callable = _Callable
    Mapping = _Mapping

from sortipy.common import MissingConfigurationError, require_env_var
from sortipy.domain.data_integration import FetchScrobblesResult, LastFmScrobbleSource
from sortipy.domain.types import Album, Artist, Provider, Scrobble, Track

log = getLogger(__name__)


LASTFM_BASE_URL = "https://ws.audioscrobbler.com/2.0/"


type ImageSize = Literal["small", "medium", "large", "extralarge"]
ArtistPayload = TypedDict("ArtistPayload", {"mbid": str, "#text": str})
Image = TypedDict("Image", {"size": ImageSize, "#text": str})
AlbumPayload = TypedDict("AlbumPayload", {"mbid": str, "#text": str})
Date = TypedDict("Date", {"uts": str, "#text": str})
# date: DD MMM YYYY, HH:MM


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


RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
RETRYABLE_ERROR_CODES = {16, 29}
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_BACKOFF_INITIAL = 0.5
DEFAULT_BACKOFF_FACTOR = 2.0
DEFAULT_BACKOFF_MAX = 8.0


@dataclass(frozen=True)
class RetryConfiguration:
    """Configuration values for Last.fm retry behaviour."""

    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    backoff_initial: float = DEFAULT_BACKOFF_INITIAL
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR
    backoff_max: float = DEFAULT_BACKOFF_MAX


class LastFmAPIError(RuntimeError):
    """Raised when the Last.fm API returns an application-level error."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class HttpLastFmScrobbleSource(LastFmScrobbleSource):
    """HTTP implementation of the Last.fm scrobble source port."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        user_name: str | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] | None = None,
        retry: RetryConfiguration | None = None,
    ) -> None:
        self._api_key = _coalesce_credential("LASTFM_API_KEY", api_key)
        self._user_name = _coalesce_credential("LASTFM_USER_NAME", user_name)
        self._client = client or httpx.Client()
        self._sleep = sleep or time.sleep
        retry_config = retry or RetryConfiguration()
        self._max_attempts = max(1, retry_config.max_attempts)
        self._backoff_initial = max(retry_config.backoff_initial, 0.0)
        self._backoff_factor = max(retry_config.backoff_factor, 1.0)
        self._backoff_max = max(retry_config.backoff_max, self._backoff_initial)

    def fetch_recent(
        self,
        *,
        page: int = 1,
        limit: int = 200,
        from_ts: int | None = None,
        to_ts: int | None = None,
        extended: bool = False,
    ) -> FetchScrobblesResult:
        payloads, attrs = self._request_recent_scrobbles(
            page=page,
            limit=limit,
            from_ts=from_ts,
            to_ts=to_ts,
            extended=extended,
        )

        scrobbles: list[Scrobble] = []
        now_playing: Scrobble | None = None
        for payload in payloads:
            if payload.get("@attr", {}).get("nowplaying") == "true":
                now_playing = parse_scrobble(payload)
                continue
            scrobbles.append(parse_scrobble(payload))

        page_number = int(attrs["page"])
        total_pages = int(attrs["totalPages"])

        return FetchScrobblesResult(
            scrobbles=scrobbles,
            page=page_number,
            total_pages=total_pages,
            now_playing=now_playing,
        )

    def _request_recent_scrobbles(
        self,
        *,
        page: int,
        limit: int,
        from_ts: int | None,
        to_ts: int | None,
        extended: bool,
    ) -> tuple[list[TrackPayload], ResponseAttr]:
        params = {
            "method": "user.getrecenttracks",
            "user": self._user_name,
            "limit": limit,
            "page": page,
            "api_key": self._api_key,
            "format": "json",
        }
        if from_ts is not None:
            params["from"] = from_ts
        if to_ts is not None:
            params["to"] = to_ts
        if extended:
            params["extended"] = 1

        response_json = self._perform_request_with_retry(params)
        recent = response_json["recenttracks"]
        return recent["track"], recent["@attr"]

    def _perform_request_with_retry(
        self, params: Mapping[str, int | str]
    ) -> RecentTracksResponse:
        query_params = httpx.QueryParams(params)
        for attempt in range(1, self._max_attempts + 1):
            response: httpx.Response | None = None
            try:
                response = self._client.get(LASTFM_BASE_URL, params=query_params)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if not self._should_retry_status(status_code) or attempt == self._max_attempts:
                    raise
                delay = self._compute_backoff(attempt, exc.response.headers.get("Retry-After"))
                log.warning(
                    "Last.fm request failed with status %s; retrying in %.2fs (attempt %s/%s)",
                    status_code,
                    delay,
                    attempt,
                    self._max_attempts,
                )
                self._sleep(delay)
                continue
            except httpx.RequestError as exc:
                if attempt == self._max_attempts:
                    raise
                delay = self._compute_backoff(attempt, None)
                log.warning(
                    "Last.fm request error %s; retrying in %.2fs (attempt %s/%s)",
                    exc,
                    delay,
                    attempt,
                    self._max_attempts,
                )
                self._sleep(delay)
                continue

            payload = response.json()
            if isinstance(payload, dict) and "error" in payload:
                error_payload = cast(LastFmErrorResponse, payload)
                error_code = error_payload.get("error")
                message = error_payload.get("message", "Last.fm API error")
                if (
                    isinstance(error_code, int)
                    and self._should_retry_error(error_code)
                    and attempt < self._max_attempts
                ):
                    delay = self._compute_backoff(attempt, None)
                    log.warning(
                        "Last.fm returned error %s (%s); retrying in %.2fs (attempt %s/%s)",
                        error_code,
                        message,
                        delay,
                        attempt,
                        self._max_attempts,
                    )
                    self._sleep(delay)
                    continue
                raise LastFmAPIError(
                    message,
                    code=error_code if isinstance(error_code, int) else None,
                )

            if not isinstance(payload, dict) or "recenttracks" not in payload:
                raise LastFmAPIError("Unexpected Last.fm response payload")

            return cast(RecentTracksResponse, payload)

        raise LastFmAPIError("Exceeded retry attempts for Last.fm request")

    def _should_retry_status(self, status_code: int) -> bool:
        return status_code in RETRYABLE_STATUS_CODES

    def _should_retry_error(self, error_code: int) -> bool:
        return error_code in RETRYABLE_ERROR_CODES

    def _compute_backoff(self, attempt: int, retry_after_header: str | None) -> float:
        retry_after = _parse_retry_after(retry_after_header)
        if retry_after is not None:
            return min(retry_after, self._backoff_max)
        base = self._backoff_initial * (self._backoff_factor ** (attempt - 1))
        return min(base, self._backoff_max)


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            target = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if target.tzinfo is None:
            target = target.replace(tzinfo=UTC)
        seconds = (target - datetime.now(UTC)).total_seconds()
    return max(seconds, 0.0)


def parse_scrobble(scrobble: TrackPayload) -> Scrobble:
    if "@attr" in scrobble and scrobble["@attr"]["nowplaying"] == "true":
        timestamp = datetime.now(UTC)
    elif "date" in scrobble:
        timestamp = datetime.fromtimestamp(int(scrobble["date"]["uts"]), tz=UTC)
    else:
        raise ValueError("Invalid scrobble")

    try:
        track = parse_track(scrobble)
    except Exception:
        log.exception("Error parsing scrobble")
        raise

    listen = Scrobble(timestamp=timestamp, track=track, provider=Provider.LASTFM)
    track.add_scrobble(listen)
    return listen


def parse_track(track: TrackPayload) -> Track:
    artist = Artist(
        id=None,
        name=track["artist"]["#text"],
        mbid=track["artist"]["mbid"] or None,
        playcount=None,
    )
    artist.add_source(Provider.LASTFM)

    album = Album(
        id=None,
        name=track["album"]["#text"],
        artist=artist,
        mbid=track["album"]["mbid"] or None,
        playcount=None,
    )
    album.add_source(Provider.LASTFM)

    track_entity = Track(
        id=None,
        name=track["name"],
        artist=artist,
        album=album,
        mbid=track["mbid"] or None,
        playcount=None,
    )
    track_entity.add_source(Provider.LASTFM)
    album.add_track(track_entity)
    if track_entity not in artist.tracks:
        artist.tracks.append(track_entity)
    if album not in artist.albums:
        artist.albums.append(album)
    return track_entity

def _coalesce_credential(env_name: str, override: str | None) -> str:
    if override is not None:
        trimmed = override.strip()
        if not trimmed:
            raise MissingConfigurationError(f"{env_name} must not be blank")
        return trimmed
    return require_env_var(env_name)
