"""Data storage configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

APP_DIR_NAME: Final[str] = "sortipy"
DEFAULT_DB_FILENAME: Final[str] = "sortipy.db"
HTTP_CACHE_FILENAME: Final[str] = "http_cache.db"


@dataclass(frozen=True, slots=True)
class StorageConfig:
    data_dir: Path
    database_filename: str = DEFAULT_DB_FILENAME
    http_cache_filename: str = HTTP_CACHE_FILENAME

    def resolve_data_dir(self) -> Path:
        return self.data_dir.expanduser().resolve()

    def ensure_data_dir(self) -> Path:
        data_dir = self.resolve_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    def database_path(self, *, ensure: bool = True) -> Path:
        base = self.ensure_data_dir() if ensure else self.resolve_data_dir()
        return base / self.database_filename

    def http_cache_path(self, *, ensure: bool = True) -> Path:
        base = self.ensure_data_dir() if ensure else self.resolve_data_dir()
        return base / self.http_cache_filename

    def database_uri(self) -> str:
        return f"sqlite+pysqlite:///{self.database_path()}"


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    uri: str


def _default_data_dir() -> Path:
    if os.name == "nt":
        base = os.getenv("LOCALAPPDATA")
        base_path = Path(base) if base else (Path.home() / "AppData" / "Local")
    else:
        base = os.getenv("XDG_DATA_HOME")
        base_path = Path(base) if base else (Path.home() / ".local" / "share")
    return (base_path / APP_DIR_NAME).expanduser().resolve()


def get_storage_config() -> StorageConfig:
    env_dir = os.getenv("SORTIPY_DATA_DIR")
    data_dir = Path(env_dir) if env_dir else _default_data_dir()
    return StorageConfig(data_dir=data_dir)


def get_database_config(*, storage: StorageConfig | None = None) -> DatabaseConfig:
    env_uri = os.getenv("DATABASE_URI")
    if env_uri:
        return DatabaseConfig(uri=env_uri)
    storage_config = storage or get_storage_config()
    return DatabaseConfig(uri=storage_config.database_uri())
