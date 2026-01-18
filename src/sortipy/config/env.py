"""Environment variable loaders for configuration."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .errors import MissingConfigurationError

if TYPE_CHECKING:
    from collections.abc import Sequence


def require_env_vars(names: Sequence[str]) -> dict[str, str]:
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
