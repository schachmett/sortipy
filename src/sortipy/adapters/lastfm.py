"""Fetch data from Last.fm API."""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from logging import getLogger
from typing import TYPE_CHECKING, Callable, Literal, NotRequired, TypedDict, cast  # noqa: UP035

import httpx

from sortipy.common import ConfigurationError, MissingConfigurationError, require_env_var
from sortipy.domain.ports.fetching import PlayEventFetcher, PlayEventFetchResult
from sortipy.domain.types import (
    Artist,
    ArtistRole,
    CanonicalEntityType,
    ExternalID,
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

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ConfigurationError("RetryConfiguration.max_attempts must be >= 1")
        if self.backoff_initial < 0:
            raise ConfigurationError("RetryConfiguration.backoff_initial must be >= 0")
        if self.backoff_factor < 1:
            raise ConfigurationError("RetryConfiguration.backoff_factor must be >= 1")
        if self.backoff_max < self.backoff_initial:
            raise ConfigurationError("RetryConfiguration.backoff_max must be >= backoff_initial")


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


class ResponseCache:
    def __init__(self, config: CacheConfiguration, now: Callable[[], float]) -> None:
        self._enabled = config.ttl_seconds > 0 and config.max_entries > 0
        self._ttl = max(config.ttl_seconds, 0.0)
        self._max_entries = max(config.max_entries, 1) if self._enabled else 0
        self._now = now
        self._entries: OrderedDict[CacheKey, CacheEntry] = OrderedDict()

    def get(self, key: CacheKey) -> RecentTracksResponse | None:
        if not self._enabled:
            return None
        entry = self._entries.get(key)
        if entry is None:
            return None
        if self._now() >= entry.expires_at:
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return entry.response

    def store(self, key: CacheKey, response: RecentTracksResponse) -> None:
        if not self._enabled:
            return
        self._entries[key] = CacheEntry(response=response, expires_at=self._now() + self._ttl)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def should_cache(self, response: RecentTracksResponse) -> bool:
        if not self._enabled:
            return False
        for track in response["recenttracks"]["track"]:
            attrs = track.get("@attr")
            if attrs and attrs.get("nowplaying") == "true":
                return False
        return True


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


@dataclass(frozen=True)
class _ClientContext:
    api_key: str
    user_name: str
    client: httpx.Client
    retry_config: RetryConfiguration
    cache_config: CacheConfiguration
    sleep: Callable[[float], None]
    now: Callable[[], float]


def build_http_lastfm_fetcher(
    *,
    api_key: str | None = None,
    user_name: str | None = None,
    client: httpx.Client | None = None,
    options: LastFmRuntimeOptions | None = None,
) -> PlayEventFetcher:
    runtime = options or LastFmRuntimeOptions()
    retry_config = runtime.retry or RetryConfiguration()
    context = _ClientContext(
        api_key=_coalesce_credential("LASTFM_API_KEY", api_key),
        user_name=_coalesce_credential("LASTFM_USER_NAME", user_name),
        client=client or httpx.Client(),
        retry_config=retry_config,
        cache_config=runtime.cache or CacheConfiguration(),
        sleep=runtime.sleep or time.sleep,
        now=runtime.time_provider or time.time,
    )
    cache = ResponseCache(context.cache_config, context.now)

    def fetcher(
        *,
        batch_size: int = 200,
        since: datetime | None = None,
        until: datetime | None = None,
        max_events: int | None = None,
    ) -> PlayEventFetchResult:
        return _fetch_play_events(
            context,
            cache,
            batch_size=batch_size,
            since=since,
            until=until,
            max_events=max_events,
        )

    return fetcher


if TYPE_CHECKING:
    _fetcher_check: PlayEventFetcher = build_http_lastfm_fetcher(
        api_key="",
        user_name="",
        client=httpx.Client(),
    )


def _fetch_play_events(
    context: _ClientContext,
    cache: ResponseCache,
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

    while True:
        payloads, attrs = _request_recent_scrobbles(
            context,
            cache,
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
                    return PlayEventFetchResult(events=events, now_playing=now_playing)

        total_pages = int(attrs["totalPages"])
        if page >= total_pages:
            break
        page += 1
        from_ts = None

    return PlayEventFetchResult(events=events, now_playing=now_playing)


def _request_recent_scrobbles(
    context: _ClientContext,
    cache: ResponseCache,
    *,
    page: int,
    limit: int,
    from_ts: int | None,
    to_ts: int | None,
    extended: bool,
) -> tuple[list[TrackPayload], ResponseAttr]:
    params: dict[str, str | int] = {
        "method": "user.getrecenttracks",
        "user": context.user_name,
        "limit": limit,
        "page": page,
        "api_key": context.api_key,
        "format": "json",
    }
    if from_ts is not None:
        params["from"] = from_ts
    if to_ts is not None:
        params["to"] = to_ts
    if extended:
        params["extended"] = 1

    query_params = httpx.QueryParams(params)
    cache_key: CacheKey = tuple(query_params.multi_items())
    cached = cache.get(cache_key)
    if cached is not None:
        recent = cached["recenttracks"]
        return recent["track"], recent["@attr"]

    response_json = _perform_request_with_retry(context, query_params)
    if cache.should_cache(response_json):
        cache.store(cache_key, response_json)
    recent = response_json["recenttracks"]
    return recent["track"], recent["@attr"]


def _perform_request_with_retry(
    context: _ClientContext,
    params: httpx.QueryParams,
) -> RecentTracksResponse:
    attempts = context.retry_config.max_attempts
    for attempt in range(1, attempts + 1):
        response: httpx.Response | None = None
        try:
            response = context.client.get(LASTFM_BASE_URL, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if not _should_retry_status(status_code) or attempt == attempts:
                raise
            delay = _compute_backoff(context, attempt, exc.response.headers.get("Retry-After"))
            log.warning(
                "Last.fm request failed with status %s; retrying in %.2fs (attempt %s/%s)",
                status_code,
                delay,
                attempt,
                attempts,
            )
            context.sleep(delay)
            continue
        except httpx.RequestError as exc:
            if attempt == attempts:
                raise
            delay = _compute_backoff(context, attempt, None)
            log.warning(
                "Last.fm transport error %r; retrying in %.2fs (attempt %s/%s)",
                exc,
                delay,
                attempt,
                attempts,
            )
            context.sleep(delay)
            continue

        payload = response.json()
        if isinstance(payload, dict) and "error" in payload:
            error_payload = cast(LastFmErrorResponse, payload)
            error_code = error_payload.get("error")
            message = error_payload.get("message", "Last.fm API error")
            if (
                isinstance(error_code, int)
                and _should_retry_error(error_code)
                and attempt < attempts
            ):
                delay = _compute_backoff(context, attempt, None)
                log.warning(
                    "Last.fm API error %s (%s); retrying in %.2fs (attempt %s/%s)",
                    error_code,
                    message,
                    delay,
                    attempt,
                    attempts,
                )
                context.sleep(delay)
                continue
            detail = f"{error_code}: {message}" if isinstance(error_code, int) else message
            log.error("Last.fm API error %s", detail)
            raise LastFmAPIError(
                message,
                code=error_code if isinstance(error_code, int) else None,
            ) from None

        if not isinstance(payload, dict) or "recenttracks" not in payload:
            raise LastFmAPIError("Unexpected Last.fm response payload")

        return cast(RecentTracksResponse, payload)

    raise LastFmAPIError("Exceeded retry attempts for Last.fm request")


def _should_retry_status(status_code: int) -> bool:
    return status_code in RETRYABLE_STATUS_CODES


def _should_retry_error(error_code: int) -> bool:
    return error_code in RETRYABLE_ERROR_CODES


def _compute_backoff(
    context: _ClientContext,
    attempt: int,
    retry_after_header: str | None,
) -> float:
    retry_after = _parse_retry_after(retry_after_header)
    if retry_after is not None:
        return min(retry_after, context.retry_config.backoff_max)
    base = context.retry_config.backoff_initial * (
        context.retry_config.backoff_factor ** (attempt - 1)
    )
    return min(base, context.retry_config.backoff_max)


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
        played_at = datetime.now(UTC)
    elif "date" in scrobble:
        played_at = datetime.fromtimestamp(int(scrobble["date"]["uts"]), tz=UTC)
    else:
        raise ValueError("Invalid scrobble")

    try:
        artist, release_set, _release, recording, track = _parse_entities(scrobble)
    except Exception:
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

    # Ensure bidirectional references stay aligned for primary artist relationships.
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
        artist.add_external_id(
            ExternalID(
                namespace=ExternalNamespace.MUSICBRAINZ_ARTIST.value,
                value=artist_mbid,
                entity_type=CanonicalEntityType.ARTIST,
                provider=Provider.MUSICBRAINZ,
            )
        )
    artist.sources.add(Provider.LASTFM)

    album_name = payload["album"]["#text"]
    album_mbid = payload["album"]["mbid"] or None
    release_set = ReleaseSet(title=album_name)
    release_set.sources.add(Provider.LASTFM)
    if album_mbid:
        release_set.add_external_id(
            ExternalID(
                namespace=ExternalNamespace.MUSICBRAINZ_RELEASE_GROUP.value,
                value=album_mbid,
                entity_type=CanonicalEntityType.RELEASE_SET,
                provider=Provider.MUSICBRAINZ,
            )
        )

    release = Release(title=album_name or payload["name"], release_set=release_set)
    release.sources.add(Provider.LASTFM)
    if album_mbid:
        release.add_external_id(
            ExternalID(
                namespace=ExternalNamespace.MUSICBRAINZ_RELEASE.value,
                value=album_mbid,
                entity_type=CanonicalEntityType.RELEASE,
                provider=Provider.MUSICBRAINZ,
            )
        )

    track_mbid = payload.get("mbid") or None
    recording = Recording(title=payload["name"])
    recording.sources.add(Provider.LASTFM)
    if track_mbid:
        recording.add_external_id(
            ExternalID(
                namespace=ExternalNamespace.MUSICBRAINZ_RECORDING.value,
                value=track_mbid,
                entity_type=CanonicalEntityType.RECORDING,
                provider=Provider.MUSICBRAINZ,
            )
        )

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


def _coalesce_credential(env_name: str, override: str | None) -> str:
    if override is not None:
        trimmed = override.strip()
        if not trimmed:
            raise MissingConfigurationError(f"{env_name} must not be blank")
        return trimmed
    return require_env_var(env_name)
