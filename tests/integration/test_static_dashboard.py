"""Integration tests for the packaged-build surface.

- ``/api/*`` mirrors: same handlers as the public routes, but with the
  ``{error}`` JSON shape the static dashboard client expects.
- Static dashboard serving: HTML key injection, per-route index files,
  SPA/404 fallback, traversal containment, API priority over the catch-all.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.api.config import Settings, settings_from_env
from services.api.dashboard import inject_key
from services.api.main import create_app

API_KEY = "test-key"
AUTH = {"X-API-Key": API_KEY}

INDEX_HTML = "<html><head><title>app</title></head><body>APP_SHELL</body></html>"


def make_client(tmp_path: Path, **overrides: object) -> TestClient:
    values: dict = {
        "env": "development",
        "api_key": API_KEY,
        "database_url": f"sqlite:///{tmp_path / 'test.db'}",
        "cors_origins": (),
        "auto_run": False,
    }
    values.update(overrides)
    return TestClient(create_app(Settings(**values)))


def make_export(tmp_path: Path) -> Path:
    """Fake a Next static export (trailingSlash layout) on disk."""
    root = tmp_path / "out"
    (root / "_next" / "static").mkdir(parents=True)
    (root / "tasks").mkdir()
    (root / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (root / "tasks" / "index.html").write_text(
        "<html><head></head><body>TASK_VIEW</body></html>", encoding="utf-8"
    )
    (root / "404.html").write_text(
        "<html><head></head><body>NOT_FOUND_PAGE</body></html>", encoding="utf-8"
    )
    (root / "_next" / "static" / "chunk.js").write_text("console.log(1)", "utf-8")
    (tmp_path / "outside.txt").write_text("SECRET_OUTSIDE", encoding="utf-8")
    return root


# --- /api mirrors -----------------------------------------------------------


def test_api_mirror_requires_key(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        assert client.get("/api/tasks").status_code == 401
        assert client.get("/api/agents").status_code == 401
        assert client.get("/api/settings/providers").status_code == 401


def test_api_mirror_returns_error_shape(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        missing = client.get("/api/tasks/nope", headers=AUTH)
        # The public route keeps FastAPI's default shape for comparison.
        public = client.get("/tasks/nope", headers=AUTH)

    assert missing.status_code == 404
    assert missing.json() == {"error": "task not found"}
    assert public.json() == {"detail": "task not found"}


def test_api_mirror_validation_uses_error_shape(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        mirrored = client.post("/api/tasks", json={}, headers=AUTH)
        public = client.post("/tasks", json={}, headers=AUTH)

    assert mirrored.status_code == 422
    assert mirrored.json() == {"error": "validation failed"}
    assert "detail" in public.json()


def test_api_mirror_list_and_agents_and_settings(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        created = client.post(
            "/api/tasks", json={"title": "mirror task"}, headers=AUTH
        )
        listed = client.get("/api/tasks", headers=AUTH).json()
        agents = client.get("/api/agents", headers=AUTH).json()
        providers = client.get("/api/settings/providers", headers=AUTH).json()

    assert created.status_code == 201
    assert listed["count"] == 1
    assert listed["items"][0]["title"] == "mirror task"
    assert agents["count"] > 0
    assert {item["provider"] for item in providers["items"]} >= {"google", "ollama"}


def test_api_mirror_unknown_path_is_json_404_not_html(tmp_path: Path) -> None:
    export = make_export(tmp_path)
    with make_client(tmp_path, dashboard_dir=str(export)) as client:
        response = client.get("/api/definitely-not-a-route", headers=AUTH)
    assert response.status_code == 404
    assert response.json() == {"error": "not found"}


# --- static dashboard serving ----------------------------------------------


def test_api_only_mode_has_no_root_page(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        assert client.get("/").status_code == 404


def test_root_serves_injected_app_shell(tmp_path: Path) -> None:
    export = make_export(tmp_path)
    with make_client(tmp_path, dashboard_dir=str(export)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "APP_SHELL" in response.text
    assert f'window.__WF_KEY="{API_KEY}"' in response.text


def test_route_index_served_for_extensionless_path(tmp_path: Path) -> None:
    export = make_export(tmp_path)
    with make_client(tmp_path, dashboard_dir=str(export)) as client:
        response = client.get("/tasks/")

    assert response.status_code == 200
    assert "TASK_VIEW" in response.text
    assert "window.__WF_KEY" in response.text


def test_static_asset_served_verbatim(tmp_path: Path) -> None:
    export = make_export(tmp_path)
    with make_client(tmp_path, dashboard_dir=str(export)) as client:
        response = client.get("/_next/static/chunk.js")

    assert response.status_code == 200
    assert response.text == "console.log(1)"
    assert "__WF_KEY" not in response.text


def test_unknown_path_falls_back_to_404_page(tmp_path: Path) -> None:
    export = make_export(tmp_path)
    with make_client(tmp_path, dashboard_dir=str(export)) as client:
        response = client.get("/some/unknown/route")

    assert response.status_code == 404
    assert "NOT_FOUND_PAGE" in response.text


def test_api_routes_win_over_dashboard_catch_all(tmp_path: Path) -> None:
    export = make_export(tmp_path)
    with make_client(tmp_path, dashboard_dir=str(export)) as client:
        health = client.get("/health")
        docs = client.get("/docs")
        tasks = client.get("/api/tasks", headers=AUTH)

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert docs.status_code == 200
    assert tasks.status_code == 200
    assert "items" in tasks.json()


@pytest.mark.parametrize("path", ["/../outside.txt", "/%2e%2e/outside.txt"])
def test_path_traversal_never_escapes_export_dir(
    path: str, tmp_path: Path
) -> None:
    export = make_export(tmp_path)
    with make_client(tmp_path, dashboard_dir=str(export)) as client:
        response = client.get(path)

    assert "SECRET_OUTSIDE" not in response.text


def test_no_key_configured_means_no_injection(tmp_path: Path) -> None:
    export = make_export(tmp_path)
    with make_client(tmp_path, api_key=None, dashboard_dir=str(export)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "__WF_KEY" not in response.text


def test_inject_key_without_head_tag_prepends_tag() -> None:
    assert inject_key("<body>x</body>", "k").startswith("<script>")


# --- settings ---------------------------------------------------------------


def test_dashboard_dir_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFORCE_DASHBOARD_DIR", "C:/app/out")
    assert settings_from_env().dashboard_dir == "C:/app/out"


def test_dashboard_dir_defaults_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKFORCE_DASHBOARD_DIR", raising=False)
    assert settings_from_env().dashboard_dir is None
