"""Provider registry, model-name resolution and credential discovery.

Model names follow the LiteLLM convention ``provider/model`` (the first
slash separates the two parts, so ``openrouter/meta-llama/llama-3`` stays
valid). Credentials are discovered from environment variables and are
never printed or returned in error messages.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class UnknownProviderError(ValueError):
    """Raised when a model name names a provider we do not know."""


@dataclass(frozen=True)
class ProviderSpec:
    """Static description of one model provider."""

    name: str
    api_key_env: str


PROVIDERS: dict[str, ProviderSpec] = {
    spec.name: spec
    for spec in (
        ProviderSpec("openai", "OPENAI_API_KEY"),
        ProviderSpec("anthropic", "ANTHROPIC_API_KEY"),
        ProviderSpec("google", "GEMINI_API_KEY"),
        ProviderSpec("groq", "GROQ_API_KEY"),
        ProviderSpec("mistral", "MISTRAL_API_KEY"),
        ProviderSpec("openrouter", "OPENROUTER_API_KEY"),
    )
}


@dataclass(frozen=True)
class ResolvedModel:
    """A validated ``provider/model`` reference."""

    provider: str
    model: str

    @property
    def name(self) -> str:
        """The full LiteLLM-style model name."""
        return f"{self.provider}/{self.model}"


def resolve_model(name: str) -> ResolvedModel:
    """Parse ``provider/model`` and validate the provider part."""
    provider, separator, model = name.partition("/")
    if not separator or not provider or not model:
        raise UnknownProviderError(
            f"model name must look like 'provider/model', got: {name!r}"
        )
    if provider not in PROVIDERS:
        known = ", ".join(sorted(PROVIDERS))
        raise UnknownProviderError(
            f"unknown provider {provider!r} in {name!r} (known: {known})"
        )
    return ResolvedModel(provider=provider, model=model)


def credential_for(provider: str) -> str | None:
    """Return the provider's API key from the environment, or ``None``.

    Fail-open discovery: a missing key simply marks the provider as
    unavailable; the router then skips it instead of erroring. The key
    itself is never included in exceptions or logs.
    """
    spec = PROVIDERS.get(provider)
    if spec is None:
        return None
    value = os.environ.get(spec.api_key_env, "").strip()
    return value or None
