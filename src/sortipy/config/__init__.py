"""Application configuration helpers."""

from __future__ import annotations

from .env import require_env_vars
from .errors import ConfigurationError, MissingConfigurationError
from .http_resilience import CacheConfig, RateLimit, ResilienceConfig, RetryPolicy
from .lastfm import LastFmConfig, get_lastfm_config
from .logging import configure_logging
from .spotify import (
    DEFAULT_SPOTIFY_SCOPES,
    SPOTIFY_CURRENTLY_PLAYING_SCOPES,
    SPOTIFY_RECENTLY_PLAYED_SCOPES,
    SpotifyConfig,
    get_spotify_config,
    merge_spotify_scopes,
)
from .storage import DatabaseConfig, StorageConfig, get_database_config, get_storage_config

__all__ = [
    "DEFAULT_SPOTIFY_SCOPES",
    "SPOTIFY_CURRENTLY_PLAYING_SCOPES",
    "SPOTIFY_RECENTLY_PLAYED_SCOPES",
    "CacheConfig",
    "ConfigurationError",
    "DatabaseConfig",
    "LastFmConfig",
    "MissingConfigurationError",
    "RateLimit",
    "ResilienceConfig",
    "RetryPolicy",
    "SpotifyConfig",
    "StorageConfig",
    "configure_logging",
    "get_database_config",
    "get_lastfm_config",
    "get_spotify_config",
    "get_storage_config",
    "merge_spotify_scopes",
    "require_env_vars",
]
