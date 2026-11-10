"""Integration tests for the FastAPI service (health, auth, task CRUD)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.api.config import Settings
from services.api.main import create_app

API_KEY = "test-key"


def make_client(tmp_path: Path, **overrides: object) -> TestClient:
    """Build a client with an isolated SQLite database per test."""
    values: dict = {
        "env": "development",
        "api_key": API_KEY,
        "database_url": f"sqlite:///{tmp_path / 'test.db'}",
        "cors_origins": (),
    }
    values.update(overrides)
    return TestClient(create_app(Settings(**values)))


# --- health -----------------------------------------------------------------


def test_health_is_public(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_security_headers_present(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


# --- authentication ---------------------------------------------------------


def test_tasks_reject_missing_key(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        assert client.get("/tasks").status_code == 401


def test_tasks_reject_wrong_key(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/tasks", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_production_without_key_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="WORKFORCE_API_KEY"):
        create_app(
            Settings(env="production", api_key=None, database_url="sqlite:///:memory:")
        )


def test_development_without_key_is_open(tmp_path: Path) -> None:
    with make_client(tmp_path, api_key=None) as client:
        response = client.post("/tasks", json={"title": "open dev"})
    assert response.status_code == 201


# --- task CRUD --------------------------------------------------------------


def test_task_crud_flow(tmp_path: Path) -> None:
    headers = {"X-API-Key": API_KEY}
    with make_client(tmp_path) as client:
        # create
        created = client.post(
            "/tasks",
            json={"title": "Build dashboard", "description": "Next.js scaffold"},
            headers=headers,
        )
        assert created.status_code == 201
        task_id = created.json()["id"]
        assert created.json()["status"] == "pending"

        # read
        fetched = client.get(f"/tasks/{task_id}", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["title"] == "Build dashboard"

        # list
        listed = client.get("/tasks", headers=headers)
        assert listed.status_code == 200
        assert listed.json()["count"] == 1

        # update
        updated = client.patch(
            f"/tasks/{task_id}",
            json={"status": "completed", "result": "done"},
            headers=headers,
        )
        assert updated.status_code == 200
        assert updated.json()["status"] == "completed"
        assert updated.json()["result"] == "done"

        # delete
        deleted = client.delete(f"/tasks/{task_id}", headers=headers)
        assert deleted.status_code == 204
        assert client.get(f"/tasks/{task_id}", headers=headers).status_code == 404


def test_get_missing_task_is_404(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get(
            "/tasks/does-not-exist", headers={"X-API-Key": API_KEY}
        )
    assert response.status_code == 404


def test_list_filters_by_status(tmp_path: Path) -> None:
    headers = {"X-API-Key": API_KEY}
    with make_client(tmp_path) as client:
        client.post("/tasks", json={"title": "one"}, headers=headers)
        client.post("/tasks", json={"title": "two"}, headers=headers)
        pending = client.get("/tasks?status=pending", headers=headers)
        completed = client.get("/tasks?status=completed", headers=headers)
    assert pending.json()["count"] == 2
    assert completed.json()["count"] == 0


@pytest.mark.parametrize(
    "url",
    [
        "/tasks?status=bogus",
        "/tasks?limit=0",
        "/tasks?limit=500",
    ],
)
def test_list_validation_errors(tmp_path: Path, url: str) -> None:
    with make_client(tmp_path) as client:
        response = client.get(url, headers={"X-API-Key": API_KEY})
    assert response.status_code == 422


def test_empty_patch_is_422(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        created = client.post(
            "/tasks", json={"title": "x"}, headers={"X-API-Key": API_KEY}
        )
        task_id = created.json()["id"]
        response = client.patch(
            f"/tasks/{task_id}", json={}, headers={"X-API-Key": API_KEY}
        )
    assert response.status_code == 422


# --- agents -----------------------------------------------------------------


def test_agents_reject_missing_key(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        assert client.get("/agents").status_code == 401


def test_agents_lists_registry(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/agents", headers={"X-API-Key": API_KEY})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == len(body["items"]) > 0
    ids = [agent["id"] for agent in body["items"]]
    assert len(ids) == len(set(ids)), "duplicate agent ids"
    for agent in body["items"]:
        assert agent["name"]
        assert agent["department"]
        # prompt text must never leak through the API
        assert "prompt" not in agent
        assert "prompt_path" not in agent


def test_agents_expose_expected_roles(tmp_path: Path) -> None:
    from agents.registry import agent_ids

    with make_client(tmp_path) as client:
        body = client.get(
            "/agents", headers={"X-API-Key": API_KEY}
        ).json()
    assert {a["id"] for a in body["items"]} == set(agent_ids())
