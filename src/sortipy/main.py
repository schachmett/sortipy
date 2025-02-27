#!/usr/bin/env python3

# ruff: noqa: T201

from __future__ import annotations

import sys
from dataclasses import dataclass
from signal import SIGINT, signal
from typing import TYPE_CHECKING, cast

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

from sortipy.adapters.spotipy import SavedAlbums

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import FrameType

    from spotipy.client import Spotify


# Configuration constants
DEFAULT_FETCH_LIMIT = 200
BATCH_SIZE = 50
SPOTIFY_SCOPE = "user-library-read"


@dataclass
class Album:
    """Represents a Spotify album with essential metadata."""

    release_date: str
    title: str
    artists: str

    def __str__(self) -> str:
        """Return a formatted string representation of the album."""
        return f"{self.release_date} - {self.title} - {self.artists}"


class SpotifyAlbumFetcher:
    """Handles fetching and processing of Spotify saved albums."""

    def __init__(self, spotify_client: Spotify, fetch_limit: int = DEFAULT_FETCH_LIMIT) -> None:
        self.spotify = spotify_client
        self.fetch_limit = fetch_limit

    def fetch_albums(self) -> Iterator[Album]:
        """Generator that yields album items from Spotify API."""
        response = cast(SavedAlbums, self.spotify.current_user_saved_albums(limit=BATCH_SIZE))  # type: ignore[reportUnknownMemberType]
        total_albums = response["total"]
        fetched_count = 0
        call_number = 1

        print(f"Total albums: {total_albums} - fetching only {self.fetch_limit}...")

        while True:
            items = response["items"]
            fetched_count += len(items)
            print(f"Fetched {fetched_count}/{self.fetch_limit} albums... ({call_number})")
            for item in items:
                yield Album(
                    title=item["album"]["name"],
                    artists=", ".join(artist["name"] for artist in item["album"]["artists"]),
                    release_date=item["album"]["release_date"],
                )

            if not response["next"] or fetched_count >= self.fetch_limit:
                break

            response = cast(SavedAlbums, self.spotify.next(response))  # type: ignore[reportUnknownMemberType]
            call_number += 1


def setup_spotify_client() -> Spotify:
    """Initialize and return an authenticated Spotify client."""
    load_dotenv()
    return spotipy.Spotify(auth_manager=SpotifyOAuth(scope=SPOTIFY_SCOPE))


def display_albums(albums: list[Album]) -> None:
    """Display the albums in a formatted manner."""
    sorted_albums = sorted(albums, key=lambda x: x.release_date, reverse=True)
    for album in sorted_albums:
        print(str(album))


def main() -> None:
    """Main application entry point."""
    try:
        spotify = setup_spotify_client()
        fetcher = SpotifyAlbumFetcher(spotify)
        albums = fetcher.fetch_albums()
        display_albums(list(albums))
    except Exception as e:  # noqa: BLE001
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def sigint_handler(_signal_received: int, _frame: FrameType | None) -> None:
    """Handle SIGINT (Ctrl+C) gracefully."""
    print("\nClosed by user (Ctrl+C)")
    sys.exit(0)


if __name__ == "__main__":
    signal(SIGINT, sigint_handler)
    main()
