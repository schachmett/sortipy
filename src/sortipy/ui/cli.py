#!/usr/bin/env python3

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta
from signal import SIGINT, signal
from typing import TYPE_CHECKING

from dotenv import load_dotenv

from sortipy.app import sync_lastfm_play_events
from sortipy.config.logging import configure_logging
from sortipy.domain.data_integration import DEFAULT_SYNC_BATCH_SIZE
from sortipy.domain.model import User

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from types import FrameType

log = logging.getLogger(__name__)


# def display_albums(albums: list[LastFMAlbum]) -> None:
#     """Display the albums in a formatted manner."""
#     sorted_albums = sorted(albums, key=lambda x: x.release_date, reverse=True)
#     for album in sorted_albums:
#         print(str(album))


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synchronise Last.fm scrobbles")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_SYNC_BATCH_SIZE,
        help="Number of events to request per API call (default: %(default)s)",
    )
    parser.add_argument(
        "--user-name",
        type=str,
        required=True,
        help="Display name / Last.fm username to attach to imported play events",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        help="Maximum number of events to fetch before stopping",
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


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _compute_time_bounds(
    args: argparse.Namespace,
    *,
    now_provider: Callable[[], datetime] = _utcnow,
) -> tuple[datetime | None, datetime | None]:
    start = _parse_iso_datetime(args.start) if args.start else None
    end = _parse_iso_datetime(args.end) if args.end else None

    lookback: timedelta | None = None
    if args.lookback_hours is not None:
        if args.lookback_hours < 0:
            raise ValueError("Lookback hours must be non-negative")
        lookback = timedelta(hours=args.lookback_hours)

    if lookback is not None:
        anchor = end or now_provider()
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=UTC)
        anchor = anchor.astimezone(UTC)
        start_from_lookback = anchor - lookback
        start = start_from_lookback if start is None else max(start, start_from_lookback)
        if end is None:
            end = anchor

    if start and end and start > end:
        raise ValueError("Time window start must be before end")

    return start, end


def main(argv: Sequence[str] | None = None) -> None:
    """Main application entry point."""
    configure_logging()
    parsed_args: argparse.Namespace
    args_list = list(argv) if argv is not None else list(sys.argv[1:])
    try:
        parsed_args = _parse_args(args_list)
        start, end = _compute_time_bounds(parsed_args)
    except ValueError:
        log.exception("CLI validation error")
        sys.exit(2)

    try:
        sync_lastfm_play_events(
            user=User(display_name=parsed_args.user_name, lastfm_user=parsed_args.user_name),
            batch_size=parsed_args.batch_size,
            max_events=parsed_args.max_events,
            from_timestamp=start,
            to_timestamp=end,
        )

    except Exception:
        log.exception("Fatal error during sync")
        sys.exit(1)


def sigint_handler(_signal_received: int, _frame: FrameType | None) -> None:
    """Handle SIGINT (Ctrl+C) gracefully."""
    log.info("Closed by user (Ctrl+C)")
    sys.exit(0)


if __name__ == "__main__":
    load_dotenv()
    signal(SIGINT, sigint_handler)
    main()
