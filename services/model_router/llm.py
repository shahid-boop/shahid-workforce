"""Real LLM calls through LiteLLM: provider-agnostic, free-tier friendly.

The router picks an ordered model chain (``WORKFORCE_MODEL_PRIMARY`` plus
``WORKFORCE_MODEL_FALLBACKS``, defaulting to known free-tier models), drops
models whose API key is not in the environment, and rotates to the next
model when a call fails transiently.

Two rules keep the wiring honest:

1. Provider names are ours (``google/...``); LiteLLM expects ``gemini/...``,
   so the prefix is mapped on the way out (everything else passes through,
   including OpenRouter's nested ``provider/model:free`` ids).
2. Request-shape errors (LiteLLM ``BadRequestError`` and its subclasses:
   invalid request, content policy, context window) become
   :class:`ProviderRejectedError` and abort the chain - every provider
   would reject them too. Everything else (rate limits, timeouts, auth,
   5xx, unknown model ids) becomes :class:`ProviderError` and advances.

API keys are passed explicitly to LiteLLM, never logged, and redacted from
any error message that reaches the caller.
"""

from __future__ import annotations

import logging
import os

import litellm
import litellm.exceptions as litellm_exceptions

from services.model_router.budgets import TaskBudget
from services.model_router.fallback import ProviderError, ProviderRejectedError
from services.model_router.providers import (
    base_url_for,
    credential_for,
    resolve_model,
)
from services.model_router.router import (
    TextCall,
    available_chain,
    build_chain,
    complete,
)

logger = logging.getLogger(__name__)

# Free-tier model catalog (verified Nov 2026). Provider lists rotate over
# time; an id that disappears simply fails over to the next chain entry.
# Providers with no free tier are listed so the catalog stays complete.
FREE_TIER_MODELS: dict[str, tuple[str, ...]] = {
    "google": (
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-3-flash",
        "gemini-3.1-flash-lite",
    ),
    "groq": (
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
    ),
    "openrouter": (
        "nvidia/nemotron-3.5-lightning:free",
        "nvidia/nemotron-3.5-super-vl:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "openrouter/free",
    ),
    "mistral": (),
    "openai": (),
    "anthropic": (),
    # Local models are free by definition; the daemon must be running and
    # the provider configured (settings page or OLLAMA_BASE_URL).
    "ollama": ("llama3.2", "qwen2.5-coder"),
}

DEFAULT_PRIMARY = "google/gemini-2.5-flash"
DEFAULT_FALLBACKS: tuple[str, ...] = (
    "groq/llama-3.3-70b-versatile",
    "openrouter/nvidia/nemotron-3.5-lightning:free",
)

# Our provider names -> LiteLLM prefixes (verified with get_llm_provider).
PROVIDER_PREFIX_OVERRIDES: dict[str, str] = {"google": "gemini"}

# Request-shape/content errors: no other provider would accept them either.
_FATAL_LITELLM = (litellm_exceptions.BadRequestError,)


def configured_primary() -> str:
    """Primary model from ``WORKFORCE_MODEL_PRIMARY`` (or the free default)."""
    return os.environ.get("WORKFORCE_MODEL_PRIMARY", "").strip() or DEFAULT_PRIMARY


def configured_fallbacks() -> tuple[str, ...]:
    """Fallback chain from ``WORKFORCE_MODEL_FALLBACKS`` (comma-separated)."""
    raw = os.environ.get("WORKFORCE_MODEL_FALLBACKS", "").strip()
    if not raw:
        return DEFAULT_FALLBACKS
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def litellm_model(name: str) -> str:
    """Translate our ``provider/model`` name to LiteLLM's expected form."""
    resolved = resolve_model(name)
    prefix = PROVIDER_PREFIX_OVERRIDES.get(resolved.provider, resolved.provider)
    return f"{prefix}/{resolved.model}"


def _redact(text: str, api_key: str | None) -> str:
    """Never let a key through in an error message."""
    if api_key and api_key in text:
        return text.replace(api_key, "***")
    return text


def _classify(exc: BaseException, api_key: str | None) -> Exception:
    """Map a LiteLLM exception onto the router's error taxonomy."""
    message = _redact(str(exc), api_key)
    if isinstance(exc, _FATAL_LITELLM):
        return ProviderRejectedError(f"request rejected: {message}")
    # Rate limits, timeouts, auth failures, 5xx and unknown model ids are
    # all worth retrying on the next model of the chain.
    return ProviderError(f"provider failed: {message}")


def _extract_text(response: object, model: str) -> str:
    """Pull the assistant text out of a LiteLLM response object."""
    choices = getattr(response, "choices", None)
    if not choices:
        raise ProviderError(f"{model}: response contained no choices")
    content = getattr(getattr(choices[0], "message", None), "content", None)
    if not isinstance(content, str) or not content.strip():
        raise ProviderError(f"{model}: response contained no text content")
    return content


async def litellm_call(
    model: str,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    timeout: float = 60.0,
) -> str:
    """Call one model through LiteLLM and return its text response.

    Raises :class:`ProviderRejectedError` for request-shape errors and
    :class:`ProviderError` for everything else, so the fallback chain can
    decide whether to rotate. The API key never appears in any exception.
    """
    resolved = resolve_model(model)
    api_key = credential_for(resolved.provider)
    if api_key is None:
        raise ProviderError(f"no API key configured for provider {resolved.provider!r}")
    base = base_url_for(resolved.provider)

    try:
        if base is not None:
            response = await litellm.acompletion(
                model=litellm_model(model),
                messages=messages,
                api_key=api_key,
                base_url=base,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        else:
            response = await litellm.acompletion(
                model=litellm_model(model),
                messages=messages,
                api_key=api_key,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
    except Exception as exc:  # classified into the router's error taxonomy
        raise _classify(exc, api_key) from exc
    return _extract_text(response, model)


def text_call(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    timeout: float = 60.0,
) -> TextCall:
    """Bind a prompt to the router's ``TextCall`` signature (model -> text)."""

    async def call(model: str) -> str:
        return await litellm_call(
            model,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

    return call


async def complete_messages(
    messages: list[dict[str, str]],
    *,
    agent_model: str | None = None,
    budget: TaskBudget | None = None,
) -> str | None:
    """Run ``messages`` through the configured chain.

    Returns ``None`` when no provider in the chain has a credential - the
    caller then falls back to its non-LLM placeholder. If credentials do
    exist but every model fails, the error propagates instead of being
    silently swallowed.
    """
    primary = configured_primary()
    fallbacks = configured_fallbacks()
    chain = build_chain(primary, agent_model=agent_model, fallbacks=fallbacks)
    if not available_chain(chain):
        logger.info("no provider credentials configured; LLM call skipped")
        return None

    text, decision, attempts = await complete(
        text_call(messages),
        primary=primary,
        agent_model=agent_model,
        fallbacks=fallbacks,
        budget=budget,
    )
    if attempts:
        logger.warning(
            "llm call via %s after %d failed attempt(s): %s",
            decision.model,
            len(attempts),
            "; ".join(f"{a.model}: {a.error}" for a in attempts),
        )
    else:
        logger.info("llm call via %s", decision.model)
    return text


__all__ = [
    "DEFAULT_FALLBACKS",
    "DEFAULT_PRIMARY",
    "FREE_TIER_MODELS",
    "complete_messages",
    "configured_fallbacks",
    "configured_primary",
    "litellm_call",
    "litellm_model",
    "text_call",
]
