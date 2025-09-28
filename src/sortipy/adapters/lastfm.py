"""Fetch data from Last.fm API."""

from __future__ import annotations

from datetime import UTC, datetime
from logging import getLogger
from typing import Literal, NotRequired, TypedDict, cast

import httpx

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


class HttpLastFmScrobbleSource(LastFmScrobbleSource):
    """HTTP implementation of the Last.fm scrobble source port."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        user_name: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = _coalesce_credential("LASTFM_API_KEY", api_key)
        self._user_name = _coalesce_credential("LASTFM_USER_NAME", user_name)
        self._client = client or httpx.Client()

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

        response = self._client.get(LASTFM_BASE_URL, params=params)
        response.raise_for_status()
        response_json = cast(RecentTracksResponse, response.json())
        recent = response_json["recenttracks"]
        return recent["track"], recent["@attr"]


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
