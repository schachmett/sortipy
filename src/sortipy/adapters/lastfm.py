"""Fetch data from Last.fm API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from logging import getLogger
from typing import Literal, TypedDict, cast

import httpx

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


class Track(TypedDict):
    artist: Artist
    streamable: Literal["0", "1"]
    image: list[Image]
    mbid: str
    album: Album
    name: str
    url: str
    date: Date


class ResponseAttr(TypedDict):
    user: str
    totalPages: str
    page: str
    perPage: str
    total: str


RecentTracks = TypedDict("RecentTracks", {"track": list[Track], "@attr": ResponseAttr})


class RecentTracksResponse(TypedDict):
    recenttracks: RecentTracks


def get_recent_tracks(page: int, limit: int = 100) -> list[Track]:
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


@dataclass
class LastFMTrack:
    track_name: str
    track_mbid: str
    artist_name: str
    artist_mbid: str
    album_name: str
    album_mbid: str
    url: str
    date: datetime


def parse_track(track: Track) -> LastFMTrack:
    return LastFMTrack(
        track_name=track["name"],
        track_mbid=track["mbid"],
        artist_name=track["artist"]["#text"],
        artist_mbid=track["artist"]["mbid"],
        album_name=track["album"]["#text"],
        album_mbid=track["album"]["mbid"],
        url=track["url"],
        date=datetime.fromtimestamp(int(track["date"]["uts"]), tz=UTC),
    )
