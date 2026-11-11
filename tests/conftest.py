"""Shared test fixtures.

Provider API keys are cleared for every test: the default agent runner
must be deterministic whether or not the developer's shell happens to
carry real credentials. Tests that need a key set it explicitly with
``monkeypatch.setenv``.
"""

from __future__ import annotations

import pytest

from services.model_router.providers import PROVIDERS

# Every provider key env var, derived from the registry so a new provider
# is covered automatically.
PROVIDER_KEY_ENVS = tuple(sorted({spec.api_key_env for spec in PROVIDERS.values()}))


@pytest.fixture(autouse=True)
def clear_provider_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all provider credentials from the environment for one test."""
    for env_name in PROVIDER_KEY_ENVS:
        monkeypatch.delenv(env_name, raising=False)
    # Also hide our own model selection so defaults are exercised.
    monkeypatch.delenv("WORKFORCE_MODEL_PRIMARY", raising=False)
    monkeypatch.delenv("WORKFORCE_MODEL_FALLBACKS", raising=False)
