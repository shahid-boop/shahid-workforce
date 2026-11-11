"""Integration tests for dev auto-run: create a task, it executes inline.

``Settings.auto_run`` (dev default on, production default off, overridable
via ``WORKFORCE_AUTO_RUN``) makes ``POST /tasks`` schedule an inline run
after the response. The conftest fixture clears every provider key, so the
run uses the deterministic template fallback - no network in tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.api.config import Settings, settings_from_env
from services.api.main import create_app

API_KEY = "test-key"
AUTH = {"X-API-Key": API_KEY}


def make_client(tmp_path: Path, **overrides: object) -> TestClient:
    """Build a client with an isolated SQLite database per test."""
    values: dict = {
        "env": "development",
        "api_key": API_KEY,
        "database_url": f"sqlite:///{tmp_path / 'test.db'}",
        "cors_origins": (),
        "auto_run": True,
    }
    values.update(overrides)
    return TestClient(create_app(Settings(**values)))


def test_created_task_runs_inline_when_auto_run_enabled(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        created = client.post(
            "/tasks",
            json={"title": "Draft status report", "description": "summarize"},
            headers=AUTH,
        )
        assert created.status_code == 201
        task_id = created.json()["id"]

        # TestClient runs sync background tasks before returning, so the
        # task is already executed by the time we re-read it.
        task = client.get(f"/tasks/{task_id}", headers=AUTH).json()

    assert task["status"] == "completed"
    assert task["result"]  # compose_result joins "## <agent>" sections
    assert task["result"].startswith("## ")


def test_created_task_stays_pending_without_auto_run(tmp_path: Path) -> None:
    with make_client(tmp_path, auto_run=False) as client:
        created = client.post(
            "/tasks", json={"title": "Wait for worker"}, headers=AUTH
        )
        task_id = created.json()["id"]
        task = client.get(f"/tasks/{task_id}", headers=AUTH).json()

    assert created.json()["status"] == "pending"
    assert task["status"] == "pending"
    assert task["result"] is None


def test_auto_run_failure_marks_task_failed_not_500(tmp_path: Path) -> None:
    """A crashing run is recorded on the task; the create call still 201s."""
    from unittest.mock import patch

    with make_client(tmp_path) as client:
        with patch(
            "services.api.routes.tasks.execute_task_async",
            side_effect=RuntimeError("boom"),
        ):
            created = client.post(
                "/tasks", json={"title": "Doomed"}, headers=AUTH
            )
        assert created.status_code == 201
        # Background failure was swallowed (logged) - the row still exists.
        assert client.get(
            f"/tasks/{created.json()['id']}", headers=AUTH
        ).status_code == 200


# --- settings_from_env ------------------------------------------------------


def test_auto_run_defaults_to_on_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WORKFORCE_ENV", raising=False)
    monkeypatch.delenv("WORKFORCE_AUTO_RUN", raising=False)
    assert settings_from_env().auto_run is True


def test_auto_run_defaults_to_off_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKFORCE_ENV", "production")
    monkeypatch.setenv("WORKFORCE_API_KEY", "prod-key")
    monkeypatch.delenv("WORKFORCE_AUTO_RUN", raising=False)
    assert settings_from_env().auto_run is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1", True), ("true", True), ("yes", True), ("on", True),
     ("0", False), ("false", False), ("no", False), ("off", False)],
)
def test_auto_run_env_override(
    value: str, expected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WORKFORCE_AUTO_RUN", value)
    monkeypatch.setenv("WORKFORCE_ENV", "production")
    monkeypatch.setenv("WORKFORCE_API_KEY", "prod-key")
    assert settings_from_env().auto_run is expected


def test_auto_run_override_wins_over_development_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dev can still force queued mode for testing the worker path."""
    monkeypatch.delenv("WORKFORCE_ENV", raising=False)
    monkeypatch.setenv("WORKFORCE_AUTO_RUN", "0")
    assert settings_from_env().auto_run is False
