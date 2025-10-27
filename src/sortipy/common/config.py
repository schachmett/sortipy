"""Utilities for loading application configuration."""

from __future__ import annotations

import os


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
