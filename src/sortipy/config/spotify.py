"""Spotify configuration values."""

from __future__ import annotations

from dataclasses import dataclass, field

from .env import require_env_vars

DEFAULT_SPOTIFY_SCOPES = (
    "user-library-read",
    "user-follow-read",
)

SPOTIFY_RECENTLY_PLAYED_SCOPES = ("user-read-recently-played",)
SPOTIFY_CURRENTLY_PLAYING_SCOPES = (
    "user-read-currently-playing",
    "user-read-playback-state",
)


def merge_spotify_scopes(*scopes: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    for scope_list in scopes:
        for scope in scope_list:
            if scope not in merged:
                merged.append(scope)
    return tuple(merged)


@dataclass(frozen=True)
class SpotifyConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    scope: tuple[str, ...] = field(default_factory=lambda: DEFAULT_SPOTIFY_SCOPES)
    cache_path: str | None = None


def get_spotify_config(*, scope: tuple[str, ...] | None = None) -> SpotifyConfig:
    values = require_env_vars(
        (
            "SPOTIFY_CLIENT_ID",
            "SPOTIFY_CLIENT_SECRET",
            "SPOTIFY_REDIRECT_URI",
            "SPOTIFY_CACHE_PATH",
        )
    )
    return SpotifyConfig(
        client_id=values["SPOTIFY_CLIENT_ID"],
        client_secret=values["SPOTIFY_CLIENT_SECRET"],
        redirect_uri=values["SPOTIFY_REDIRECT_URI"],
        scope=scope or DEFAULT_SPOTIFY_SCOPES,
        cache_path=values["SPOTIFY_CACHE_PATH"],
    )
