from __future__ import annotations

import os

import pytest

from sortipy.common.config import MissingConfigurationError, require_env_var, require_env_vars


def test_require_env_vars_returns_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXAMPLE_VAR", "value")

    result = require_env_vars(["EXAMPLE_VAR"])

    assert result["EXAMPLE_VAR"] == "value"


def test_require_env_vars_raises_when_any_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_VAR", raising=False)

    with pytest.raises(MissingConfigurationError) as exc:
        require_env_vars(["MISSING_VAR"])

    assert "MISSING_VAR" in str(exc.value)


def test_require_env_var_handles_blank_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXAMPLE_VAR", "   ")

    with pytest.raises(MissingConfigurationError):
        require_env_var("EXAMPLE_VAR")


def test_require_env_vars_restores_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEMP_VAR", "123")

    assert os.getenv("TEMP_VAR") == "123"
    result = require_env_var("TEMP_VAR")
    assert result == "123"
