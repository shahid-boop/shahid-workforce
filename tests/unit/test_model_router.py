"""Tests for the model router: providers, budgets, fallback and routing."""

from __future__ import annotations

import asyncio

import pytest

from services.model_router.budgets import (
    BudgetExceededError,
    TaskBudget,
    UnknownPriceError,
    estimate_cost_usd,
    estimate_tokens,
    price_for,
)
from services.model_router.fallback import (
    NoProviderAvailableError,
    ProviderError,
    ProviderRejectedError,
    call_with_fallback,
)
from services.model_router.providers import (
    UnknownProviderError,
    credential_for,
    resolve_model,
)
from services.model_router.router import (
    available_chain,
    build_chain,
    complete,
    route,
)

OPENAI_KEY = "OPENAI_API_KEY"
ANTHROPIC_KEY = "ANTHROPIC_API_KEY"


# --- providers --------------------------------------------------------------


def test_resolve_model_splits_provider_and_model() -> None:
    resolved = resolve_model("openai/gpt-4o-mini")
    assert resolved.provider == "openai"
    assert resolved.model == "gpt-4o-mini"
    assert resolved.name == "openai/gpt-4o-mini"


def test_resolve_model_allows_extra_slashes_in_model() -> None:
    resolved = resolve_model("openrouter/meta-llama/llama-3.3-70b")
    assert resolved.provider == "openrouter"
    assert resolved.model == "meta-llama/llama-3.3-70b"


def test_resolve_model_rejects_missing_slash() -> None:
    with pytest.raises(UnknownProviderError, match="provider/model"):
        resolve_model("gpt-4o-mini")


def test_resolve_model_rejects_unknown_provider() -> None:
    with pytest.raises(UnknownProviderError, match="unknown provider"):
        resolve_model("nonsense/model")


def test_credential_for_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(OPENAI_KEY, "sk-test")
    assert credential_for("openai") == "sk-test"


def test_credential_for_missing_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ANTHROPIC_KEY, raising=False)
    assert credential_for("anthropic") is None


def test_credential_for_unknown_provider_is_none() -> None:
    assert credential_for("nonsense") is None


# --- budgets --------------------------------------------------------------


def test_estimate_tokens_scales_with_length() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 400) == 100


def test_price_for_known_and_unknown_models() -> None:
    assert price_for("openai/gpt-4o-mini").input_per_million == 0.15
    with pytest.raises(UnknownPriceError, match="no price known"):
        price_for("openai/some-new-model")


def test_estimate_cost_uses_price_table() -> None:
    # 1M input @ $0.15 + 1M output @ $0.60 = $0.75
    cost = estimate_cost_usd("openai/gpt-4o-mini", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.75)


def test_budget_preflight_allows_within_ceiling() -> None:
    budget = TaskBudget(ceiling_usd=1.0)
    cost = budget.preflight("openai/gpt-4o-mini", 100_000, 10_000)
    assert cost > 0
    assert budget.remaining_usd == pytest.approx(1.0)


def test_budget_preflight_blocks_over_ceiling() -> None:
    budget = TaskBudget(ceiling_usd=0.01)
    with pytest.raises(BudgetExceededError, match="exceed task ceiling"):
        budget.preflight("openai/gpt-4o", 1_000_000, 1_000_000)


def test_budget_charge_reduces_remaining() -> None:
    budget = TaskBudget(ceiling_usd=1.0)
    budget.charge("openai/gpt-4o-mini", 0.25)
    assert budget.spent_usd == pytest.approx(0.25)
    assert budget.remaining_usd == pytest.approx(0.75)
    assert budget.charges == [("openai/gpt-4o-mini", 0.25)]


def test_budget_preflight_unknown_price_is_free_not_error() -> None:
    budget = TaskBudget(ceiling_usd=0.01)
    assert budget.preflight("openai/unpriced-model", 1_000_000, 1_000_000) == 0.0


# --- fallback --------------------------------------------------------------


def test_call_with_fallback_returns_first_success() -> None:
    calls: list[str] = []

    async def call(model: str) -> str:
        calls.append(model)
        return f"ok:{model}"

    result = asyncio.run(
        call_with_fallback(["openai/gpt-4o-mini", "groq/llama-3.3-70b-versatile"], call)
    )
    assert result.value == "ok:openai/gpt-4o-mini"
    assert result.attempts == ()
    assert calls == ["openai/gpt-4o-mini"]


def test_call_with_fallback_rotates_on_provider_error() -> None:
    calls: list[str] = []

    async def call(model: str) -> str:
        calls.append(model)
        if model.startswith("openai"):
            raise ProviderError("rate limited")
        return "recovered"

    result = asyncio.run(
        call_with_fallback(["openai/gpt-4o-mini", "groq/llama-3.3-70b-versatile"], call)
    )
    assert result.value == "recovered"
    assert result.model == "groq/llama-3.3-70b-versatile"
    assert [a.model for a in result.attempts] == ["openai/gpt-4o-mini"]
    assert "rate limited" in result.attempts[0].error
    assert calls == ["openai/gpt-4o-mini", "groq/llama-3.3-70b-versatile"]


def test_call_with_fallback_fatal_error_does_not_rotate() -> None:
    calls: list[str] = []

    async def call(model: str) -> str:
        calls.append(model)
        raise ProviderRejectedError("bad request")

    with pytest.raises(ProviderRejectedError, match="bad request"):
        asyncio.run(
            call_with_fallback(["openai/gpt-4o-mini", "groq/llama-3.3-70b-versatile"], call)
        )
    assert calls == ["openai/gpt-4o-mini"]  # second model never tried


def test_call_with_fallback_exhausted_raises_with_detail() -> None:
    async def call(model: str) -> str:
        raise ConnectionError(f"down: {model}")

    with pytest.raises(NoProviderAvailableError, match="all models failed") as exc:
        asyncio.run(
            call_with_fallback(["openai/gpt-4o-mini", "groq/llama-3.3-70b-versatile"], call)
        )
    assert "openai/gpt-4o-mini" in str(exc.value)
    assert "groq/llama-3.3-70b-versatile" in str(exc.value)


def test_call_with_fallback_empty_chain_raises() -> None:
    async def call(model: str) -> str:
        return model

    with pytest.raises(NoProviderAvailableError, match="empty fallback chain"):
        asyncio.run(call_with_fallback([], call))


# --- router ----------------------------------------------------------------


def test_build_chain_orders_override_primary_fallbacks_and_dedupes() -> None:
    chain = build_chain(
        "openai/gpt-4o-mini",
        agent_model="anthropic/claude-3-5-sonnet",
        fallbacks=["groq/llama-3.3-70b-versatile", "openai/gpt-4o-mini"],
    )
    assert chain == (
        "anthropic/claude-3-5-sonnet",
        "openai/gpt-4o-mini",
        "groq/llama-3.3-70b-versatile",
    )


def test_build_chain_rejects_provider_typo() -> None:
    with pytest.raises(UnknownProviderError, match="unknown provider"):
        build_chain("openai/gpt-4o-mini", fallbacks=["opnai/gpt-4o"])


def test_available_chain_filters_no_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OPENAI_KEY, "sk-test")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    available = available_chain(
        ("openai/gpt-4o-mini", "groq/llama-3.3-70b-versatile")
    )
    assert available == ("openai/gpt-4o-mini",)


def test_route_prefers_agent_override_when_credentialed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OPENAI_KEY, "sk-test")
    monkeypatch.setenv(ANTHROPIC_KEY, "sk-ant")

    decision = route(
        "openai/gpt-4o-mini",
        agent_model="anthropic/claude-3-5-sonnet",
        fallbacks=["groq/llama-3.3-70b-versatile"],
    )
    assert decision.model == "anthropic/claude-3-5-sonnet"
    assert decision.source == "agent-override"
    assert "groq/llama-3.3-70b-versatile" in decision.dropped_no_credential


def test_route_falls_back_to_primary_without_agent_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OPENAI_KEY, "sk-test")

    decision = route("openai/gpt-4o-mini", fallbacks=["groq/llama-3.3-70b-versatile"])
    assert decision.model == "openai/gpt-4o-mini"
    assert decision.source == "primary"


def test_route_skips_uncredentialed_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OPENAI_KEY, "sk-test")
    monkeypatch.delenv(ANTHROPIC_KEY, raising=False)

    decision = route("openai/gpt-4o-mini", agent_model="anthropic/claude-3-5-sonnet")
    assert decision.model == "openai/gpt-4o-mini"
    assert decision.source == "primary"
    assert "anthropic/claude-3-5-sonnet" in decision.dropped_no_credential


def test_route_without_any_credential_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(OPENAI_KEY, raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(NoProviderAvailableError, match="credentials configured"):
        route("openai/gpt-4o-mini", fallbacks=["groq/llama-3.3-70b-versatile"])


# --- complete --------------------------------------------------------------


def test_complete_bills_the_winning_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OPENAI_KEY, "sk-test")

    async def call(model: str) -> str:
        return "hello world"

    budget = TaskBudget(ceiling_usd=1.0)
    text, decision, attempts = asyncio.run(
        complete(
            call,
            primary="openai/gpt-4o-mini",
            budget=budget,
            input_tokens=1_000_000,
            expected_output_tokens=1_000,
        )
    )
    assert text == "hello world"
    assert decision.model == "openai/gpt-4o-mini"
    assert attempts == ()
    # 1M input @ $0.15/1M = $0.15, output estimated from "hello world" (3 tokens)
    assert budget.spent_usd > 0
    assert budget.spent_usd < 0.16


def test_complete_falls_through_then_bills_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OPENAI_KEY, "sk-test")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")

    async def call(model: str) -> str:
        if model.startswith("openai"):
            raise ProviderError("boom")
        return "recovered"

    budget = TaskBudget(ceiling_usd=1.0)
    _, decision, attempts = asyncio.run(
        complete(
            call,
            primary="openai/gpt-4o-mini",
            fallbacks=["groq/llama-3.3-70b-versatile"],
            budget=budget,
        )
    )
    assert decision.model == "groq/llama-3.3-70b-versatile"
    assert decision.source == "primary"  # override absent -> primary source
    assert [a.model for a in attempts] == ["openai/gpt-4o-mini"]
    assert budget.charges[0][0] == "groq/llama-3.3-70b-versatile"


def test_complete_preflight_blocks_over_budget_before_calling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(OPENAI_KEY, "sk-test")
    calls: list[str] = []

    async def call(model: str) -> str:
        calls.append(model)
        return "never"

    budget = TaskBudget(ceiling_usd=0.01)
    with pytest.raises(BudgetExceededError, match="exceed task ceiling"):
        asyncio.run(
            complete(
                call,
                primary="openai/gpt-4o",
                budget=budget,
                input_tokens=1_000_000,
                expected_output_tokens=1_000_000,
            )
        )
    assert calls == []  # provider was never contacted
