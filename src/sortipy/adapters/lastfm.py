"""Fetch data from Last.fm API."""

from __future__ import annotations

import os
from logging import getLogger
from pathlib import Path

import pylast

log = getLogger(__name__)

SESSION_KEY_FNAME = Path(__file__).parents[3] / ".session_key_lastfm"
API_KEY = os.getenv("LASTFM_API_KEY")
API_SECRET = os.getenv("LASTFM_API_SECRET")


def get_session_key(network: pylast.LastFMNetwork) -> str:
    """Get the session key for the Last.fm network."""
    if not SESSION_KEY_FNAME.exists():
        skg = pylast.SessionKeyGenerator(network)
        url = skg.get_web_auth_url()
        import time
        import webbrowser

        log.info(f"Please authorize this script to access your account: {url}\n")

        webbrowser.open(url)

        while True:
            try:
                session_key = skg.get_web_auth_session_key(url)
                with SESSION_KEY_FNAME.open("w") as f:
                    f.write(session_key)
                break
            except pylast.WSError:
                time.sleep(1)
    else:
        session_key = SESSION_KEY_FNAME.open("r", encoding="utf-8").read()


def get_recent_tracks() -> list[pylast.Track]:
    """Get the recent tracks for a user."""
    network = pylast.LastFMNetwork(API_KEY, API_SECRET)
    network.session_key = get_session_key(network)

    tracks = network.get_user(os.getenv("LASTFM_USER_NAME")).get_recent_tracks(limit=100)
    return tracks
