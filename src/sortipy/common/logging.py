"""Shared logging helpers for Sortipy."""

from __future__ import annotations

import logging


def configure_logging(*, level: int = logging.INFO, force: bool = False) -> None:
    """Initialise the root logger once with sensible defaults.

    Parameters mirror ``logging.basicConfig`` with a simplified contract: we default
    to INFO level and a terse format suitable for CLI output. Pass ``force=True`` to
    reconfigure during tests or specialised entry points.
    """

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        force=force,
    )

