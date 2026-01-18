"""Last.fm configuration values."""

from __future__ import annotations

from dataclasses import dataclass

from .env import require_env_vars
from .http_resilience import CacheConfig, RateLimit, ResilienceConfig, ShouldCacheHook

LASTFM_BASE_URL = "https://ws.audioscrobbler.com/2.0/"
LASTFM_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class LastFmConfig:
    """Holds Last.fm API configuration values."""

    api_key: str
    user_name: str
    resilience: ResilienceConfig


def get_lastfm_config(
    *,
    resilience: ResilienceConfig | None = None,
    cache_predicate: ShouldCacheHook | None = None,
) -> LastFmConfig:
    values = require_env_vars(("LASTFM_API_KEY", "LASTFM_USER_NAME"))
    return LastFmConfig(
        api_key=values["LASTFM_API_KEY"],
        user_name=values["LASTFM_USER_NAME"],
        resilience=resilience
        or ResilienceConfig(
            name="lastfm",
            base_url=LASTFM_BASE_URL,
            timeout_seconds=LASTFM_TIMEOUT_SECONDS,
            ratelimit=RateLimit(max_calls=4, per_seconds=1.0),
            cache=CacheConfig(backend="memory", should_cache=cache_predicate),
        ),
    )
