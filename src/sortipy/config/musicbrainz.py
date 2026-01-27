"""MusicBrainz configuration values."""

from __future__ import annotations

from dataclasses import dataclass

from .env import require_env_vars
from .http_resilience import CacheConfig, RateLimit, ResilienceConfig, RetryPolicy

DEFAULT_MUSICBRAINZ_BASE_URL = "https://musicbrainz.org/ws/2"


@dataclass(frozen=True, slots=True)
class MusicBrainzConfig:
    resilience: ResilienceConfig


def get_musicbrainz_config() -> MusicBrainzConfig:
    values = require_env_vars(("MUSICBRAINZ_APP_NAME", "MUSICBRAINZ_CONTACT"))
    app_name = values["MUSICBRAINZ_APP_NAME"]
    contact = values["MUSICBRAINZ_CONTACT"]
    user_agent = f"{app_name} ({contact})"

    resilience = ResilienceConfig(
        name="musicbrainz",
        base_url=DEFAULT_MUSICBRAINZ_BASE_URL,
        ratelimit=RateLimit(max_calls=1, per_seconds=1.0),
        retry=RetryPolicy(total=4),
        cache=CacheConfig(enabled=True, backend="memory"),
        default_headers={"User-Agent": user_agent},
    )

    return MusicBrainzConfig(resilience=resilience)
