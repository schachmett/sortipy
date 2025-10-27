"""Data storage helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

APP_DIR_NAME: Final[str] = "sortipy"
DEFAULT_DB_FILENAME: Final[str] = "sortipy.db"


def get_data_dir() -> Path:
    """Return the directory where Sortipy stores persistent data."""

    env_dir = os.getenv("SORTIPY_DATA_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA")
        base_path = Path(base) if base else (Path.home() / "AppData" / "Local")
    else:
        base = os.getenv("XDG_DATA_HOME")
        base_path = Path(base) if base else (Path.home() / ".local" / "share")

    return (base_path / APP_DIR_NAME).expanduser().resolve()


def ensure_data_dir(path: Path | None = None) -> Path:
    """Ensure the data directory exists and return it."""

    data_dir = path or get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_database_path() -> Path:
    """Return the default database path, ensuring the data directory exists."""

    data_dir = ensure_data_dir()
    return data_dir / DEFAULT_DB_FILENAME


def get_database_uri() -> str:
    """Compute the database URI, respecting overrides."""

    env_uri = os.getenv("DATABASE_URI")
    if env_uri:
        return env_uri
    db_path = get_database_path()
    return f"sqlite+pysqlite:///{db_path}"
