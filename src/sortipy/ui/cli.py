from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta
from signal import SIGINT, signal
from typing import TYPE_CHECKING
from uuid import UUID

from dotenv import load_dotenv

from sortipy.app import (
    create_user,
    enrich_musicbrainz_releases,
    sync_lastfm_play_events,
    sync_spotify_library_items,
)
from sortipy.config import configure_logging

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from types import FrameType

log = logging.getLogger(__name__)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synchronise Sortipy data")
    subparsers = parser.add_subparsers(dest="command", required=True)

    lastfm = subparsers.add_parser("lastfm", help="Sync Last.fm play events")
    lastfm.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Number of events to request per API call (defaults to config)",
    )
    lastfm.add_argument(
        "--user-id",
        type=str,
        help="Existing user id to attach to imported play events",
    )
    lastfm.add_argument(
        "--max-events",
        type=int,
        help="Maximum number of events to fetch before stopping",
    )
    lastfm.add_argument(
        "--start",
        type=str,
        help="ISO-8601 timestamp (UTC) marking the inclusive start of the window",
    )
    lastfm.add_argument(
        "--end",
        type=str,
        help="ISO-8601 timestamp (UTC) marking the inclusive end of the window",
    )
    lastfm.add_argument(
        "--lookback-hours",
        type=float,
        help="Relative lookback window in hours (overrides start if larger)",
    )

    spotify = subparsers.add_parser("spotify-library", help="Sync Spotify library items")
    spotify.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Number of items to request per API call (defaults to config)",
    )
    spotify.add_argument(
        "--user-id",
        type=str,
        help="Existing user id to attach to imported library items",
    )
    spotify.add_argument(
        "--spotify-user-id",
        type=str,
        help="Optional Spotify user id to store on the user entity",
    )
    spotify.add_argument(
        "--max-tracks",
        type=int,
        help="Maximum number of saved tracks to fetch before stopping",
    )
    spotify.add_argument(
        "--max-albums",
        type=int,
        help="Maximum number of saved albums to fetch before stopping",
    )
    spotify.add_argument(
        "--max-artists",
        type=int,
        help="Maximum number of followed artists to fetch before stopping",
    )

    musicbrainz = subparsers.add_parser(
        "musicbrainz-releases",
        help="Enrich releases using MusicBrainz",
    )
    musicbrainz.add_argument(
        "--limit",
        type=int,
        help="Maximum number of recordings to enrich",
    )

    user = subparsers.add_parser("user", help="User management commands")
    user_sub = user.add_subparsers(dest="user_command", required=True)
    user_create = user_sub.add_parser("create", help="Create a user")
    user_create.add_argument(
        "--display-name",
        type=str,
        required=True,
        help="Display name for the user",
    )
    user_create.add_argument(
        "--email",
        type=str,
        help="Optional email address",
    )
    user_create.add_argument(
        "--lastfm-user",
        type=str,
        help="Optional Last.fm username to store on the user",
    )
    user_create.add_argument(
        "--spotify-user-id",
        type=str,
        help="Optional Spotify user id to store on the user",
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


def _parse_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"Invalid UUID: {value}") from exc


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
        start, end = (None, None)
        if parsed_args.command == "lastfm":
            start, end = _compute_time_bounds(parsed_args)
    except ValueError:
        log.exception("CLI validation error")
        sys.exit(2)

    try:
        if parsed_args.command == "lastfm":
            if parsed_args.user_id is None:
                raise ValueError("Missing --user-id (create a user first)")  # noqa: TRY301
            sync_lastfm_play_events(
                user_id=_parse_uuid(parsed_args.user_id),
                batch_size=parsed_args.batch_size,
                max_events=parsed_args.max_events,
                from_timestamp=start,
                to_timestamp=end,
            )
        elif parsed_args.command == "spotify-library":
            if parsed_args.user_id is None:
                raise ValueError("Missing --user-id (create a user first)")  # noqa: TRY301
            sync_spotify_library_items(
                user_id=_parse_uuid(parsed_args.user_id),
                batch_size=parsed_args.batch_size,
                max_tracks=parsed_args.max_tracks,
                max_albums=parsed_args.max_albums,
                max_artists=parsed_args.max_artists,
            )
        elif parsed_args.command == "musicbrainz-releases":
            result = enrich_musicbrainz_releases(
                limit=parsed_args.limit,
            )
            log.info(
                "MusicBrainz enrichment finished: candidates=%s, updates=%s, applied=%s",
                result.candidates,
                result.updates,
                result.applied,
            )
        elif parsed_args.command == "user" and parsed_args.user_command == "create":
            user = create_user(
                display_name=parsed_args.display_name,
                email=parsed_args.email,
                lastfm_user=parsed_args.lastfm_user,
                spotify_user_id=parsed_args.spotify_user_id,
            )
            log.info("Created user %s", user.id)
        else:
            raise ValueError(f"Unsupported command: {parsed_args.command}")  # noqa: TRY301

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
