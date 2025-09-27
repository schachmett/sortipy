"""Fetch data from Last.fm API."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from logging import getLogger
from typing import Literal, NotRequired, TypedDict, cast

import httpx

from sortipy.domain.types import Album, Artist, Provider, Scrobble, Track

log = getLogger(__name__)


API_KEY = os.getenv("LASTFM_API_KEY")
USER_NAME = os.getenv("LASTFM_USER_NAME")
LASTFM_BASE_URL = "https://ws.audioscrobbler.com/2.0/"


###############
# Last.fm API #
###############

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


def get_recent_scrobbles(page: int, limit: int = 100) -> list[TrackPayload]:
    """Get the recent tracks for a user."""
    params = {
        "method": "user.getrecenttracks",
        "user": USER_NAME,
        "limit": limit,
        "page": page,
        "api_key": API_KEY,
        "format": "json",
    }
    response = httpx.get(LASTFM_BASE_URL, params=params)
    response.raise_for_status()
    response_json = cast(RecentTracksResponse, response.json())
    return response_json["recenttracks"]["track"]


##################
# Our own format #
##################
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
