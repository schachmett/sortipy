#!/usr/bin/env python3

# ruff: noqa: T201

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from signal import SIGINT, signal
from typing import TYPE_CHECKING

from dotenv import load_dotenv

from sortipy.app import sync_lastfm_scrobbles
from sortipy.domain.data_integration import SyncRequest
from sortipy.domain.time_windows import TimeWindow

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import FrameType


# def display_albums(albums: list[LastFMAlbum]) -> None:
#     """Display the albums in a formatted manner."""
#     sorted_albums = sorted(albums, key=lambda x: x.release_date, reverse=True)
#     for album in sorted_albums:
#         print(str(album))

def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synchronise Last.fm scrobbles")
    parser.add_argument(
        "--limit",
        type=int,
        default=SyncRequest().limit,
        help="Number of scrobbles to request per page (default: %(default)s)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        help="Maximum number of pages to fetch before stopping",
    )
    parser.add_argument(
        "--start",
        type=str,
        help="ISO-8601 timestamp (UTC) marking the inclusive start of the window",
    )
    parser.add_argument(
        "--end",
        type=str,
        help="ISO-8601 timestamp (UTC) marking the inclusive end of the window",
    )
    parser.add_argument(
        "--lookback-hours",
        type=float,
        help="Relative lookback window in hours (overrides start if larger)",
    )
    return parser.parse_args(list(argv))


def _parse_iso_datetime(value: str) -> datetime:
    try:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO timestamp: {value}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _build_time_window(args: argparse.Namespace) -> TimeWindow | None:
    start = _parse_iso_datetime(args.start) if args.start else None
    end = _parse_iso_datetime(args.end) if args.end else None
    lookback = None
    if args.lookback_hours is not None:
        if args.lookback_hours < 0:
            raise ValueError("Lookback hours must be non-negative")
        lookback = timedelta(hours=args.lookback_hours)
    if any(value is not None for value in (start, end, lookback)):
        return TimeWindow(start=start, end=end, lookback=lookback)
    return None


def main(argv: Sequence[str] | None = None) -> None:
    """Main application entry point."""
    parsed_args: argparse.Namespace
    try:
        parsed_args = _parse_args(argv or sys.argv[1:])
        window = _build_time_window(parsed_args)
        request = SyncRequest(limit=parsed_args.limit, max_pages=parsed_args.max_pages)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        sync_lastfm_scrobbles(request, time_window=window)

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
