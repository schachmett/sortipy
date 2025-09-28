#!/usr/bin/env python3

# ruff: noqa: T201

from __future__ import annotations

import sys
from signal import SIGINT, signal
from typing import TYPE_CHECKING

from dotenv import load_dotenv

from sortipy.app import sync_lastfm_scrobbles

if TYPE_CHECKING:
    from types import FrameType


# def display_albums(albums: list[LastFMAlbum]) -> None:
#     """Display the albums in a formatted manner."""
#     sorted_albums = sorted(albums, key=lambda x: x.release_date, reverse=True)
#     for album in sorted_albums:
#         print(str(album))


def main() -> None:
    """Main application entry point."""
    try:
        sync_lastfm_scrobbles()

    except Exception as e:  # noqa: BLE001
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def sigint_handler(_signal_received: int, _frame: FrameType | None) -> None:
    """Handle SIGINT (Ctrl+C) gracefully."""
    print("\nClosed by user (Ctrl+C)")
    sys.exit(0)


if __name__ == "__main__":
    load_dotenv()
    signal(SIGINT, sigint_handler)
    main()
