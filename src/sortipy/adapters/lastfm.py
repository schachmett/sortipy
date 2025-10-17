"""Fetch data from Last.fm API."""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from logging import getLogger
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict, cast

import httpx

if TYPE_CHECKING:
    from collections.abc import Callable
else:  # pragma: no cover - imported for runtime type hint resolution
    from collections.abc import Callable as _Callable

    Callable = _Callable

from sortipy.common import MissingConfigurationError, require_env_var
from sortipy.domain.data_integration import FetchPlayEventsResult, PlayEventSource
from sortipy.domain.types import Album, Artist, PlayEvent, Provider, Track

log = getLogger(__name__)


LASTFM_BASE_URL = "https://ws.audioscrobbler.com/2.0/"


def _datetime_to_epoch_seconds(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.astimezone(UTC).timestamp())


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


@dataclass(frozen=True)
class CacheConfiguration:
    """Configuration for caching Last.fm responses."""

    ttl_seconds: float = 30.0
    max_entries: int = 256


CacheKey = tuple[tuple[str, str], ...]


@dataclass
class CacheEntry:
    response: RecentTracksResponse
    expires_at: float


@dataclass(frozen=True)
class LastFmRuntimeOptions:
    """Tune runtime behaviour for the Last.fm adapter."""

    retry: RetryConfiguration | None = None
    cache: CacheConfiguration | None = None
    sleep: Callable[[float], None] | None = None
    time_provider: Callable[[], float] | None = None


class LastFmAPIError(RuntimeError):
    """Raised when the Last.fm API returns an application-level error."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class HttpLastFmPlayEventSource(PlayEventSource):
    """HTTP implementation of the Last.fm play-event source port."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        user_name: str | None = None,
        client: httpx.Client | None = None,
        options: LastFmRuntimeOptions | None = None,
    ) -> None:
        self._api_key = _coalesce_credential("LASTFM_API_KEY", api_key)
        self._user_name = _coalesce_credential("LASTFM_USER_NAME", user_name)
        self._client = client or httpx.Client()
        runtime = options or LastFmRuntimeOptions()
        self._sleep = runtime.sleep or time.sleep
        self._time = runtime.time_provider or time.time
        retry_config = runtime.retry or RetryConfiguration()
        self._max_attempts = max(1, retry_config.max_attempts)
        self._backoff_initial = max(retry_config.backoff_initial, 0.0)
        self._backoff_factor = max(retry_config.backoff_factor, 1.0)
        self._backoff_max = max(retry_config.backoff_max, self._backoff_initial)
        cache_config = runtime.cache or CacheConfiguration()
        self._cache_enabled = cache_config.ttl_seconds > 0 and cache_config.max_entries > 0
        self._cache_ttl = max(cache_config.ttl_seconds, 0.0)
        self._cache_max_entries = max(cache_config.max_entries, 1) if self._cache_enabled else 0
        self._cache: OrderedDict[CacheKey, CacheEntry] = OrderedDict()

    def fetch_recent(
        self,
        *,
        batch_size: int = 200,
        since: datetime | None = None,
        until: datetime | None = None,
        max_events: int | None = None,
    ) -> FetchPlayEventsResult:
        from_ts = _datetime_to_epoch_seconds(since) + 1 if since else None
        to_ts = _datetime_to_epoch_seconds(until) if until else None

        events: list[PlayEvent] = []
        now_playing: PlayEvent | None = None
        page = 1
        remaining = max_events

        while True:
            payloads, attrs = self._request_recent_scrobbles(
                page=page,
                limit=batch_size,
                from_ts=from_ts,
                to_ts=to_ts,
                extended=True,
            )

            for payload in payloads:
                if payload.get("@attr", {}).get("nowplaying") == "true":
                    now_playing = parse_play_event(payload)
                    continue
                event = parse_play_event(payload)
                events.append(event)
                if remaining is not None:
                    remaining -= 1
                    if remaining <= 0:
                        return FetchPlayEventsResult(events=events, now_playing=now_playing)

            total_pages = int(attrs["totalPages"])
            if page >= total_pages:
                break
            page += 1
            # Once we move past the initial page, the from bound is no longer required.
            from_ts = None

        return FetchPlayEventsResult(events=events, now_playing=now_playing)

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

        query_params = httpx.QueryParams(params)
        cache_key = self._build_cache_key(query_params)
        cached_response = self._cache_get(cache_key)
        if cached_response is not None:
            recent = cached_response["recenttracks"]
            return recent["track"], recent["@attr"]

        response_json = self._perform_request_with_retry(query_params)
        if self._should_cache_response(response_json):
            self._cache_store(cache_key, response_json)
        recent = response_json["recenttracks"]
        return recent["track"], recent["@attr"]

    def _perform_request_with_retry(self, params: httpx.QueryParams) -> RecentTracksResponse:
        for attempt in range(1, self._max_attempts + 1):
            response: httpx.Response | None = None
            try:
                response = self._client.get(LASTFM_BASE_URL, params=params)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if not self._should_retry_status(status_code) or attempt == self._max_attempts:
                    raise
                delay = self._compute_backoff(attempt, exc.response.headers.get("Retry-After"))
                log.warning(
                    f"Last.fm request failed with status {status_code}; retrying in "
                    f"{delay:.2f}s (attempt {attempt}/{self._max_attempts})"
                )
                self._sleep(delay)
                continue
            except httpx.RequestError as exc:
                if attempt == self._max_attempts:
                    raise
                delay = self._compute_backoff(attempt, None)
                log.warning(
                    f"Last.fm transport error {exc!r}; retrying in {delay:.2f}s "
                    f"(attempt {attempt}/{self._max_attempts})"
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
                        f"Last.fm API error {error_code} ({message}); retrying in {delay:.2f}s "
                        f"(attempt {attempt}/{self._max_attempts})"
                    )
                    self._sleep(delay)
                    continue
                if isinstance(error_code, int):
                    log.error(f"Last.fm API error {error_code}: {message}")
                else:
                    log.error(f"Last.fm API error: {message}")
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

    def _build_cache_key(self, query_params: httpx.QueryParams) -> CacheKey:
        return tuple(query_params.multi_items())

    def _cache_get(self, key: CacheKey) -> RecentTracksResponse | None:
        if not self._cache_enabled:
            return None
        entry = self._cache.get(key)
        if entry is None:
            return None
        if self._time() >= entry.expires_at:
            self._cache.pop(key, None)
            return None
        self._cache.move_to_end(key)
        return entry.response

    def _cache_store(self, key: CacheKey, response: RecentTracksResponse) -> None:
        if not self._cache_enabled:
            return
        expires_at = self._time() + self._cache_ttl
        self._cache[key] = CacheEntry(response=response, expires_at=expires_at)
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_max_entries:
            self._cache.popitem(last=False)

    def _should_cache_response(self, response: RecentTracksResponse) -> bool:
        if not self._cache_enabled:
            return False
        tracks = response["recenttracks"]["track"]
        for track in tracks:
            attrs = track.get("@attr")
            if attrs and attrs.get("nowplaying") == "true":
                return False
        return True


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


def parse_play_event(scrobble: TrackPayload) -> PlayEvent:
    if "@attr" in scrobble and scrobble["@attr"]["nowplaying"] == "true":
        timestamp = datetime.now(UTC)
    elif "date" in scrobble:
        timestamp = datetime.fromtimestamp(int(scrobble["date"]["uts"]), tz=UTC)
    else:
        raise ValueError("Invalid scrobble")

    try:
        track = parse_track(scrobble)
    except Exception:
        log.exception("Error parsing play event")
        raise

    event = PlayEvent(timestamp=timestamp, track=track, provider=Provider.LASTFM)
    track.add_play_event(event)
    return event


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
