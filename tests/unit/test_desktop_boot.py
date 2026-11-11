"""Unit tests for the desktop (EXE) boot helpers."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from services.desktop import boot


def test_ensure_api_key_generates_and_persists(tmp_path: Path) -> None:
    config = tmp_path / "config.json"

    first = boot.ensure_api_key(config)
    second = boot.ensure_api_key(config)

    assert first.startswith("wh-")
    assert len(first) > 20
    assert first == second  # stable across launches
    assert json.loads(config.read_text(encoding="utf-8"))["api_key"] == first


def test_ensure_api_key_regenerates_corrupt_file(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text("{not json", encoding="utf-8")

    key = boot.ensure_api_key(config)

    assert key.startswith("wh-")
    assert json.loads(config.read_text(encoding="utf-8"))["api_key"] == key


def test_ensure_api_key_regenerates_empty_field(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text('{"api_key": ""}', encoding="utf-8")
    assert boot.ensure_api_key(config).startswith("wh-")


def test_dashboard_dir_env_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WORKFORCE_DASHBOARD_DIR", str(tmp_path))
    assert boot.resolve_dashboard_dir() == tmp_path


def test_dashboard_dir_none_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKFORCE_DASHBOARD_DIR", "/definitely/not/here")
    assert boot.resolve_dashboard_dir() is None


def test_dashboard_dir_finds_repo_export(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WORKFORCE_DASHBOARD_DIR", raising=False)
    found = boot.resolve_dashboard_dir()
    # Repo checkout: apps/dashboard/out when it has been built, else None.
    # (The frozen bundle path only exists inside a PyInstaller build.)
    if found is not None:
        assert (found / "index.html").is_file()
        assert "dashboard" in str(found)


def test_prepare_fills_every_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(boot, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(boot, "resolve_dashboard_dir", lambda: None)

    monkey_env: dict[str, str] = {}
    used = boot.prepare(env=monkey_env)

    assert used == tmp_path
    assert (tmp_path / "config.json").is_file()
    assert monkey_env["WORKFORCE_API_KEY"].startswith("wh-")
    assert monkey_env["WORKFORCE_DATABASE_URL"].endswith("workforce.db")
    assert monkey_env["WORKFORCE_AUTO_RUN"] == "1"
    assert monkey_env["WORKFORCE_PORT"] == str(boot.DEFAULT_PORT)
    assert monkey_env["WORKFORCE_ENV"] == "development"
    assert "WORKFORCE_DASHBOARD_DIR" not in monkey_env


def test_prepare_respects_explicit_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(boot, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(boot, "resolve_dashboard_dir", lambda: None)
    monkey_env = {
        "WORKFORCE_API_KEY": "user-supplied-key",
        "WORKFORCE_PORT": "9000",
    }

    boot.prepare(env=monkey_env)

    assert monkey_env["WORKFORCE_API_KEY"] == "user-supplied-key"
    assert monkey_env["WORKFORCE_PORT"] == "9000"
    assert monkey_env["WORKFORCE_DATABASE_URL"].endswith("workforce.db")


def test_default_port_is_not_the_dev_port() -> None:
    assert boot.DEFAULT_PORT != 8000


def test_bundle_root_in_source_is_repo_root() -> None:
    assert not boot.is_frozen()
    root = boot.bundle_root()
    assert (root / "services").is_dir()
    assert (root / "pyproject.toml").is_file()


def test_app_data_dir_layout() -> None:
    directory = boot.app_data_dir()
    if sys.platform == "win32":
        assert directory.name == "ShahidWorkforce"
        assert str(directory).startswith(str(os.environ.get("LOCALAPPDATA", "")))
    else:
        assert directory.name == ".shahid-workforce"
