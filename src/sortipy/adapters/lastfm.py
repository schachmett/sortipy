"""Fetch data from Last.fm API."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from logging import getLogger
from typing import Literal, NotRequired, TypedDict, cast

import httpx

from sortipy.domain.types import LastFMAlbum, LastFMArtist, LastFMScrobble, LastFMTrack, ObjectType

log = getLogger(__name__)


API_KEY = os.getenv("LASTFM_API_KEY")
USER_NAME = os.getenv("LASTFM_USER_NAME")
LASTFM_BASE_URL = "https://ws.audioscrobbler.com/2.0/"


###############
# Last.fm API #
###############

type ImageSize = Literal["small", "medium", "large", "extralarge"]
Artist = TypedDict("Artist", {"mbid": str, "#text": str})
Image = TypedDict("Image", {"size": ImageSize, "#text": str})
Album = TypedDict("Album", {"mbid": str, "#text": str})
Date = TypedDict("Date", {"uts": str, "#text": str})
# date: DD MMM YYYY, HH:MM


class TrackAttr(TypedDict):
    nowplaying: Literal["true"]


Track = TypedDict(
    "Track",
    {
        "artist": Artist,
        "streamable": Literal["0", "1"],
        "image": list[Image],
        "mbid": str,
        "album": Album,
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


RecentTracks = TypedDict("RecentTracks", {"track": list[Track], "@attr": ResponseAttr})


class RecentTracksResponse(TypedDict):
    recenttracks: RecentTracks


def get_recent_scrobbles(page: int, limit: int = 100) -> list[Track]:
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
def parse_scrobble(scrobble: Track) -> LastFMScrobble:
    if "@attr" in scrobble and scrobble["@attr"]["nowplaying"] == "true":
        timestamp = datetime.now(UTC)
    elif "date" in scrobble:
        timestamp = datetime.fromtimestamp(int(scrobble["date"]["uts"]), tz=UTC)
    else:
        raise ValueError("Invalid scrobble")

    try:
        return LastFMScrobble(
            timestamp=timestamp,
            track=parse_track(scrobble),
        )
    except Exception:
        log.exception("Error parsing scrobble")
        raise


def parse_track(track: Track) -> LastFMTrack:
    artist = LastFMArtist(
        id=None,
        mbid=track["artist"]["mbid"] or None,
        type=ObjectType.ARTIST,
        playcount=None,
        name=track["artist"]["#text"],
    )
    return LastFMTrack(
        id=None,
        mbid=track["mbid"] or None,
        type=ObjectType.TRACK,
        playcount=None,
        name=track["name"],
        artist=artist,
        album=LastFMAlbum(
            id=None,
            mbid=track["album"]["mbid"] or None,
            type=ObjectType.ALBUM,
            playcount=None,
            name=track["album"]["#text"],
            artist=artist,
        ),
    )
