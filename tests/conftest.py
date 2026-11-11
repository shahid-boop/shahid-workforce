"""Shared test fixtures.

Provider API keys are cleared for every test: the default agent runner
must be deterministic whether or not the developer's shell happens to
carry real credentials. Stored-key discovery is disabled too (no
database URL, no runtime override), so tests that need a key set it
explicitly with ``monkeypatch.setenv`` or through the settings API.
"""

from __future__ import annotations

import pytest

from database.repositories import credential_repository
from services.model_router.providers import PROVIDERS

# Every provider key/base-URL env var, derived from the registry so a new
# provider is covered automatically.
PROVIDER_KEY_ENVS = tuple(sorted({spec.api_key_env for spec in PROVIDERS.values()}))
PROVIDER_BASE_URL_ENVS = tuple(
    sorted(f"{provider.upper()}_BASE_URL" for provider in PROVIDERS)
)


@pytest.fixture(autouse=True)
def clear_provider_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all provider credentials from the environment for one test."""
    for env_name in (*PROVIDER_KEY_ENVS, *PROVIDER_BASE_URL_ENVS):
        monkeypatch.delenv(env_name, raising=False)
    # Also hide our own model selection so defaults are exercised.
    monkeypatch.delenv("WORKFORCE_MODEL_PRIMARY", raising=False)
    monkeypatch.delenv("WORKFORCE_MODEL_FALLBACKS", raising=False)
    # Stored-key discovery stays off unless a test creates an app (which
    # points it at that test's throwaway database).
    monkeypatch.delenv("WORKFORCE_DATABASE_URL", raising=False)
    credential_repository.set_runtime_database_url(None)
