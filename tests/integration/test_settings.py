"""Integration tests for manual provider-key management (/settings/providers).

The autouse conftest fixture clears every provider key and disables
stored-key discovery, so each test opts in explicitly - exactly like the
developer experience of a fresh install with no keys configured.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.api.config import Settings
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
    }
    values.update(overrides)
    return TestClient(create_app(Settings(**values)))


def item_for(body: dict, provider: str) -> dict:
    return next(entry for entry in body["items"] if entry["provider"] == provider)


def test_settings_requires_api_key(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        assert client.get("/settings/providers").status_code == 401
        put = client.put("/settings/providers/groq", json={"api_key": "x"})
        assert put.status_code == 401
        assert client.delete("/settings/providers/groq").status_code == 401


def test_settings_rejects_wrong_key(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.get(
            "/settings/providers", headers={"X-API-Key": "wrong"}
        )
    assert response.status_code == 401


def test_list_covers_every_provider_including_ollama(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        body = client.get("/settings/providers", headers=AUTH).json()

    providers = {entry["provider"] for entry in body["items"]}
    assert {"google", "groq", "openrouter", "mistral", "ollama"} <= providers
    assert body["count"] == len(body["items"])
    # Fresh install: nothing configured, nothing masked.
    assert all(not entry["configured"] for entry in body["items"])
    assert all(entry["key_masked"] is None for entry in body["items"])


def test_store_key_returns_masked_status_and_never_leaks(tmp_path: Path) -> None:
    secret = "gsk-manual-secret-key-123456"
    with make_client(tmp_path) as client:
        put = client.put(
            "/settings/providers/groq", json={"api_key": secret}, headers=AUTH
        )
        assert put.status_code == 200
        status = put.json()
        assert status["configured"] is True
        assert status["source"] == "stored"
        assert status["key_masked"] == "gsk-****"
        assert secret not in put.text

        listing = client.get("/settings/providers", headers=AUTH)
        assert secret not in listing.text
        groq = item_for(listing.json(), "groq")
        assert groq["key_masked"] == "gsk-****"
        assert groq["stored"] is True


def test_env_key_overrides_stored_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "env-key-always-wins")
    with make_client(tmp_path) as client:
        client.put(
            "/settings/providers/groq", json={"api_key": "stored-key"}, headers=AUTH
        )
        groq = item_for(client.get("/settings/providers", headers=AUTH).json(), "groq")

    assert groq["source"] == "env"
    assert groq["stored"] is True  # row exists, env simply wins at resolution
    assert groq["key_masked"] == "env-****"


def test_delete_removes_stored_key(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        client.put(
            "/settings/providers/openai",
            json={"api_key": "sk-manual-abcdef"},
            headers=AUTH,
        )
        deleted = client.delete("/settings/providers/openai", headers=AUTH)

        assert deleted.status_code == 200
        assert deleted.json()["configured"] is False
        assert deleted.json()["stored"] is False

        openai = item_for(client.get("/settings/providers", headers=AUTH).json(), "openai")
        assert openai["configured"] is False


def test_delete_is_idempotent(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        response = client.delete("/settings/providers/openai", headers=AUTH)
    assert response.status_code == 200


def test_unknown_provider_rejected(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        put = client.put(
            "/settings/providers/nonsense", json={"api_key": "x"}, headers=AUTH
        )
        delete = client.delete("/settings/providers/nonsense", headers=AUTH)
    assert put.status_code == 422
    assert delete.status_code == 422


def test_put_requires_key_or_base_url(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        empty = client.put("/settings/providers/openai", json={}, headers=AUTH)
        blank = client.put(
            "/settings/providers/openai", json={"api_key": "   "}, headers=AUTH
        )
    assert empty.status_code == 422
    assert blank.status_code == 422


def test_ollama_base_url_only_is_enough(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        put = client.put(
            "/settings/providers/ollama",
            json={"base_url": "http://localhost:11434"},
            headers=AUTH,
        )
        assert put.status_code == 200
        status = put.json()
        assert status["configured"] is True
        assert status["base_url"] == "http://localhost:11434"


def test_base_url_only_update_keeps_existing_key(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        client.put(
            "/settings/providers/ollama",
            json={"api_key": "ollama-manual"},
            headers=AUTH,
        )
        updated = client.put(
            "/settings/providers/ollama",
            json={"base_url": "http://127.0.0.1:11434"},
            headers=AUTH,
        )

        assert updated.status_code == 200
        assert updated.json()["key_masked"] == "olla****"
        assert updated.json()["base_url"] == "http://127.0.0.1:11434"


def test_stored_key_is_used_by_credential_resolution(tmp_path: Path) -> None:
    from services.model_router.providers import credential_for

    with make_client(tmp_path) as client:
        client.put(
            "/settings/providers/mistral",
            json={"api_key": "mistral-manual-999"},
            headers=AUTH,
        )

    # The app factory pointed credential discovery at this test's database.
    assert credential_for("mistral") == "mistral-manual-999"
    assert credential_for("openai") is None


def test_base_url_env_var_enables_ollama_without_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.model_router.providers import base_url_for, credential_for

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

    assert base_url_for("ollama") == "http://localhost:11434"
    assert credential_for("ollama") == "ollama-local"
