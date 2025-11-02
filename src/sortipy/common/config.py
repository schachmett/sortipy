"""Utilities for loading application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LastFmConfig:
    """Holds Last.fm API configuration values."""

    api_key: str
    user_name: str

    @classmethod
    def from_environment(cls) -> LastFmConfig:
        values = require_env_vars(("LASTFM_API_KEY", "LASTFM_USER_NAME"))
        return cls(api_key=values["LASTFM_API_KEY"], user_name=values["LASTFM_USER_NAME"])


class ConfigurationError(RuntimeError):
    """Raised when configuration values are invalid."""


class MissingConfigurationError(ConfigurationError):
    """Raised when required configuration values are absent or blank."""


def require_env_vars(names: list[str] | tuple[str, ...]) -> dict[str, str]:
    """Return the given environment variables or raise if any are missing/blank."""

    missing: list[str] = []
    values: dict[str, str] = {}
    for name in names:
        value = os.getenv(name)
        if value is None or not value.strip():
            missing.append(name)
            continue
        values[name] = value

    if missing:
        missing_list = ", ".join(sorted(missing))
        raise MissingConfigurationError(f"Missing configuration for: {missing_list}")

    return values


def require_env_var(name: str) -> str:
    """Return a required environment variable by name."""

    return require_env_vars([name])[name]
