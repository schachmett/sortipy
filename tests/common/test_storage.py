from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest  # noqa: TC002

from sortipy.common import storage


def test_get_data_dir_prefers_explicit_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    custom = tmp_path / "custom-data"
    monkeypatch.setenv("SORTIPY_DATA_DIR", str(custom))
    result = storage.get_data_dir()

    assert result == custom.resolve()


def test_get_database_uri_uses_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URI", "sqlite:///override.db")

    uri = storage.get_database_uri()

    assert uri == "sqlite:///override.db"


def test_get_database_uri_creates_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DATABASE_URI", raising=False)
    monkeypatch.setenv("SORTIPY_DATA_DIR", str(tmp_path / "data-dir"))

    uri = storage.get_database_uri()

    expected_path = (tmp_path / "data-dir" / storage.DEFAULT_DB_FILENAME).resolve()
    assert uri == f"sqlite+pysqlite:///{expected_path}"
    assert expected_path.parent.exists()
