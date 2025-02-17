#!/usr/bin/env python3
from __future__ import annotations

import sys
from signal import SIGINT, signal
from typing import TYPE_CHECKING

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

if TYPE_CHECKING:
    from types import FrameType


__version__ = "0.1.0"

LIMIT = 200


def main() -> None:
    load_dotenv()

    scope = "user-library-read"
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope))
    results = sp.current_user_saved_albums(limit=50)

    items = results["items"]
    call_number = 1
    print(f"Total albums: {results['total']} - fetching only {LIMIT}...")
    print(f"Fetched {len(items)}/{LIMIT} albums... ({call_number})")
    while results["next"] and len(items) < LIMIT:
        results = sp.next(results)
        items.extend(results["items"])
        call_number += 1
        print(f"Fetched {len(items)}/{LIMIT} albums... ({call_number})")

    albums = []

    for item in items:
        release_date = item["album"]["release_date"]
        title = item["album"]["name"]
        artists = ", ".join([artist["name"] for artist in item["album"]["artists"]])
        if release_date.startswith("202"):
            albums.append((release_date, title, artists))

    albums.sort(key=lambda album: album[0], reverse=True)

    for album in albums:
        print(f"{album[0]} - {album[1]} - {album[2]}")


if __name__ == "__main__":

    def sigint_handler(_signal_received: int, _frame: FrameType | None) -> None:
        print("Closed by user (Ctrl+C)")  # noqa: T201
        sys.exit()

    signal(SIGINT, sigint_handler)
    main()
