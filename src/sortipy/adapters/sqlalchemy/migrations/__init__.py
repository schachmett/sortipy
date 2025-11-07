"""Utilities for managing Alembic migrations within the SQLAlchemy adapter."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Final

from alembic import command
from alembic.config import Config

from sortipy.common.storage import get_database_uri

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[5]
PYPROJECT_PATH: Final[Path] = PROJECT_ROOT / "pyproject.toml"
MIGRATIONS_PATH: Final[Path] = Path(__file__).resolve().parent

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


def _load_pyproject_options() -> dict[str, str]:
    """Load Alembic configuration values from pyproject.toml."""

    try:
        with PYPROJECT_PATH.open("rb") as pyproject_file:
            document = tomllib.load(pyproject_file)
    except FileNotFoundError:
        return {}

    tool_section = document.get("tool", {})
    alembic_section = tool_section.get("alembic", {})
    options: dict[str, str] = {}
    for key, value in alembic_section.items():
        options[str(key)] = str(value)
    return options


def _build_config() -> Config:
    """Return an Alembic Config seeded from pyproject settings."""

    config = Config(toml_file=str(PYPROJECT_PATH))
    options = _load_pyproject_options()

    script_location = options.get("script_location")
    if script_location is None:
        script_path = MIGRATIONS_PATH
    else:
        candidate = Path(script_location)
        script_path = candidate if candidate.is_absolute() else PROJECT_ROOT / candidate
    config.set_main_option("script_location", str(script_path))

    prepend_sys_path = options.get("prepend_sys_path", ".")
    prepend_path = Path(prepend_sys_path)
    resolved_prepend = (
        prepend_path if prepend_path.is_absolute() else (PROJECT_ROOT / prepend_path)
    ).resolve()
    config.set_main_option("prepend_sys_path", str(resolved_prepend))

    if "sqlalchemy.url" in options:
        config.set_main_option("sqlalchemy.url", options["sqlalchemy.url"])
    for key, value in options.items():
        if key in {"script_location", "prepend_sys_path", "sqlalchemy.url"}:
            continue
        config.set_main_option(key, value)

    config.attributes["pyproject_options"] = options
    return config


def upgrade_head(*, engine: Engine | None = None, database_uri: str | None = None) -> None:
    """Upgrade the database schema to the latest revision."""

    config = _build_config()
    if engine is not None:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        return
    config.set_main_option("sqlalchemy.url", database_uri or get_database_uri())
    command.upgrade(config, "head")
