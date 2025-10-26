from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import inspect

from sortipy.adapters.sqlalchemy import create_all_tables, start_mappers

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


def test_start_mappers_is_idempotent() -> None:
    # First invocation happens in the sqlite_engine fixture; calling again should be harmless.
    start_mappers()
    start_mappers()


def test_create_all_tables_registers_core_tables(sqlite_engine: Engine) -> None:
    create_all_tables(sqlite_engine)
    inspector = inspect(sqlite_engine)
    table_names = set(inspector.get_table_names())
    for required in ("artist", "recording", "release", "play_event"):
        assert required in table_names
