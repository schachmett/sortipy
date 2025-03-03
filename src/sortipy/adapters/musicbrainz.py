"""MusicBrainz adapter"""

from __future__ import annotations

from logging import getLogger

import httpx

from sortipy import __version__

log = getLogger(__name__)


def get_album_info(album_mbid: str) -> dict[str, str]:
    """Get album info from MusicBrainz"""
    user_agent = f"sortipy/{__version__} ( https://github.com/schachmett/sortipy )"
    url = f"https://musicbrainz.org/ws/2/release/{album_mbid}"
    response = httpx.get(url, headers={"User-Agent": user_agent}, params={"fmt": "json"})
    response.raise_for_status()
    return response.json()
