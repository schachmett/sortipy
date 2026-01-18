"""Configuration error definitions."""

from __future__ import annotations


class ConfigurationError(RuntimeError):
    """Raised when configuration values are invalid."""


class MissingConfigurationError(ConfigurationError):
    """Raised when required configuration values are absent or blank."""
