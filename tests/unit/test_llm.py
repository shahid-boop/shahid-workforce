"""Real LLM wiring: prefix mapping, error taxonomy, free-tier config.

LiteLLM is mocked throughout - no network calls and no real keys. The
autouse fixture in ``tests/conftest.py`` strips every provider credential
first, so each test opts in explicitly with ``monkeypatch.setenv``.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast

import litellm
import litellm.exceptions as litellm_exceptions
import pytest

from agents.base_agent import AgentContext
from agents.registry import get_agent
from services.model_router.fallback import (
    NoProviderAvailableError,
    ProviderError,
    ProviderRejectedError,
    call_with_fallback,
)
from services.model_router.llm import (
    DEFAULT_FALLBACKS,
    DEFAULT_PRIMARY,
    FREE_TIER_MODELS,
    complete_messages,
    configured_fallbacks,
    configured_primary,
    litellm_call,
    litellm_model,
    text_call,
)
from services.model_router.providers import PROVIDERS, UnknownProviderError, resolve_model
from services.orchestrator.supervisor import default_agent_runner

USER_MESSAGES: list[dict[str, str]] = [{"role": "user", "content": "say hi"}]


def response_with(text: str) -> SimpleNamespace:
    """Build the parts of a LiteLLM response that ``llm.py`` reads."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
    )


def install_completion(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: object = None,
    error: Exception | None = None,
) -> dict[str, object]:
    """Replace ``litellm.acompletion`` with a recorder; return its capture."""
    captured: dict[str, object] = {}

    async def fake(**kwargs: object) -> object:
        captured.update(kwargs)
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(litellm, "acompletion", fake)
    return captured


# --- model name translation -------------------------------------------------


def test_litellm_model_maps_google_prefix_to_gemini() -> None:
    assert litellm_model("google/gemini-2.5-flash") == "gemini/gemini-2.5-flash"


def test_litellm_model_passes_other_prefixes_through() -> None:
    assert litellm_model("groq/llama-3.3-70b-versatile") == "groq/llama-3.3-70b-versatile"
    nested = "openrouter/nvidia/nemotron-3.5-lightning:free"
    assert litellm_model(nested) == nested


def test_litellm_model_rejects_unknown_provider() -> None:
    with pytest.raises(UnknownProviderError, match="unknown provider"):
        litellm_model("deepseek/some-model")


# --- free-tier catalog and configuration ------------------------------------


def test_free_tier_catalog_covers_every_registered_provider() -> None:
    assert set(FREE_TIER_MODELS) == set(PROVIDERS)


def test_default_models_are_valid_provider_references() -> None:
    for name in (DEFAULT_PRIMARY, *DEFAULT_FALLBACKS):
        resolve_model(name)  # raises on a typo


def test_default_primary_is_a_free_tier_model() -> None:
    provider, _, model = DEFAULT_PRIMARY.partition("/")
    assert model in FREE_TIER_MODELS[provider]


def test_configured_primary_defaults_to_free_tier() -> None:
    # conftest clears WORKFORCE_MODEL_* before every test
    assert configured_primary() == DEFAULT_PRIMARY


def test_configured_primary_honours_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKFORCE_MODEL_PRIMARY", "groq/llama-3.1-8b-instant")
    assert configured_primary() == "groq/llama-3.1-8b-instant"


def test_configured_fallbacks_parse_comma_separated_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKFORCE_MODEL_FALLBACKS", "groq/a, openrouter/b:free")
    assert configured_fallbacks() == ("groq/a", "openrouter/b:free")


def test_configured_fallbacks_default_when_env_unset() -> None:
    assert configured_fallbacks() == DEFAULT_FALLBACKS


# --- one direct model call --------------------------------------------------


def test_litellm_call_sends_mapped_model_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    captured = install_completion(monkeypatch, result=response_with("hello there"))

    output = asyncio.run(litellm_call("google/gemini-2.5-flash", USER_MESSAGES))

    assert output == "hello there"
    assert captured["model"] == "gemini/gemini-2.5-flash"
    assert captured["api_key"] == "gemini-test-key"
    assert captured["messages"] == USER_MESSAGES
    assert captured["temperature"] == 0.2
    assert captured["max_tokens"] == 2048
    assert captured["timeout"] == 60.0


def test_litellm_call_without_credential_raises_provider_error() -> None:
    # conftest cleared every provider key
    with pytest.raises(ProviderError, match="no API key configured"):
        asyncio.run(litellm_call("google/gemini-2.5-flash", USER_MESSAGES))


def test_rate_limit_maps_to_retryable_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    error = litellm_exceptions.RateLimitError(
        message="429 slow down",
        llm_provider="groq",
        model="llama-3.3-70b-versatile",
    )
    install_completion(monkeypatch, error=error)

    with pytest.raises(ProviderError) as excinfo:
        asyncio.run(litellm_call("groq/llama-3.3-70b-versatile", USER_MESSAGES))

    assert not isinstance(excinfo.value, ProviderRejectedError)
    assert "429 slow down" in str(excinfo.value)


def test_bad_request_maps_to_fatal_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    error = litellm_exceptions.BadRequestError(
        message="messages must be a list",
        model="gpt-4o-mini",
        llm_provider="openai",
    )
    install_completion(monkeypatch, error=error)

    with pytest.raises(ProviderRejectedError, match="messages must be a list"):
        asyncio.run(litellm_call("openai/gpt-4o-mini", USER_MESSAGES))


def test_authentication_error_stays_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dead key on one provider must rotate, not abort the chain."""
    monkeypatch.setenv("GEMINI_API_KEY", "stale-key")
    error = litellm_exceptions.AuthenticationError(
        message="invalid api key",
        llm_provider="gemini",
        model="gemini-2.5-flash",
    )
    install_completion(monkeypatch, error=error)

    with pytest.raises(ProviderError) as excinfo:
        asyncio.run(litellm_call("google/gemini-2.5-flash", USER_MESSAGES))

    assert not isinstance(excinfo.value, ProviderRejectedError)


def test_api_key_is_redacted_from_error_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "super-secret-key-42")
    install_completion(monkeypatch, error=RuntimeError("rejected key super-secret-key-42"))

    with pytest.raises(ProviderError) as excinfo:
        asyncio.run(litellm_call("groq/llama-3.3-70b-versatile", USER_MESSAGES))

    text = str(excinfo.value)
    assert "super-secret-key-42" not in text
    assert "***" in text


def test_empty_content_maps_to_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    install_completion(monkeypatch, result=response_with(""))

    with pytest.raises(ProviderError, match="no text content"):
        asyncio.run(litellm_call("google/gemini-2.5-flash", USER_MESSAGES))


def test_missing_choices_maps_to_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    install_completion(monkeypatch, result=SimpleNamespace(choices=[]))

    with pytest.raises(ProviderError, match="no choices"):
        asyncio.run(litellm_call("google/gemini-2.5-flash", USER_MESSAGES))


# --- fallback chain behaviour ----------------------------------------------


def test_chain_rotates_after_transient_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key-a")
    monkeypatch.setenv("GROQ_API_KEY", "key-b")

    async def fake(**kwargs: object) -> object:
        model = str(kwargs["model"])
        if model.startswith("gemini/"):
            raise litellm_exceptions.RateLimitError(
                message="rate limited",
                llm_provider="gemini",
                model=model,
            )
        return response_with("second model answered")

    monkeypatch.setattr(litellm, "acompletion", fake)

    result = asyncio.run(
        call_with_fallback(
            ("google/gemini-2.5-flash", "groq/llama-3.3-70b-versatile"),
            text_call(USER_MESSAGES),
        )
    )

    assert result.value == "second model answered"
    assert result.model == "groq/llama-3.3-70b-versatile"
    assert [attempt.model for attempt in result.attempts] == ["google/gemini-2.5-flash"]


def test_chain_aborts_on_rejected_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key-a")
    monkeypatch.setenv("GROQ_API_KEY", "key-b")
    calls: list[str] = []

    async def fake(**kwargs: object) -> object:
        calls.append(str(kwargs["model"]))
        raise litellm_exceptions.BadRequestError(
            message="bad request shape",
            model="m",
            llm_provider="gemini",
        )

    monkeypatch.setattr(litellm, "acompletion", fake)

    with pytest.raises(ProviderRejectedError):
        asyncio.run(
            call_with_fallback(
                ("google/gemini-2.5-flash", "groq/llama-3.3-70b-versatile"),
                text_call(USER_MESSAGES),
            )
        )

    assert calls == ["gemini/gemini-2.5-flash"]  # second model never tried


# --- complete_messages (the entry point supervisor uses) --------------------


def test_complete_messages_skips_when_no_keys() -> None:
    assert asyncio.run(complete_messages(USER_MESSAGES)) is None


def test_complete_messages_returns_llm_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key-a")
    captured = install_completion(monkeypatch, result=response_with("structured plan"))

    output = asyncio.run(complete_messages(USER_MESSAGES))

    assert output == "structured plan"
    assert captured["model"] == "gemini/gemini-2.5-flash"


def test_complete_messages_honours_agent_model_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key-a")
    monkeypatch.setenv("GROQ_API_KEY", "key-b")
    captured = install_completion(monkeypatch, result=response_with("override ok"))

    output = asyncio.run(
        complete_messages(USER_MESSAGES, agent_model="groq/llama-3.1-8b-instant")
    )

    assert output == "override ok"
    assert captured["model"] == "groq/llama-3.1-8b-instant"


def test_complete_messages_propagates_exhaustion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keys exist but every model fails: the error must surface, not template."""
    monkeypatch.setenv("GEMINI_API_KEY", "key-a")
    monkeypatch.setenv("GROQ_API_KEY", "key-b")
    install_completion(
        monkeypatch,
        error=litellm_exceptions.RateLimitError(
            message="always limited",
            llm_provider="gemini",
            model="gemini-2.5-flash",
        ),
    )

    with pytest.raises(NoProviderAvailableError, match="all models failed"):
        asyncio.run(complete_messages(USER_MESSAGES))


# --- supervisor integration -------------------------------------------------


def test_default_runner_calls_llm_when_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key-a")
    captured = install_completion(monkeypatch, result=response_with("real llm output"))

    definition = get_agent("documentation_engineer")
    ctx = AgentContext(task_id="t-llm", input="write the docs")
    output = asyncio.run(default_agent_runner(definition, ctx))

    assert output == "real llm output"
    assert captured["model"] == "gemini/gemini-2.5-flash"
    messages = cast("list[dict[str, str]]", captured["messages"])
    assert messages[0]["role"] == "system"
    assert definition.prompt in messages[0]["content"]
