"""Select the model for a call: agent override, then primary, then fallback.

Chain building rules (checked in order):

1. An explicit agent override (``agents.yaml`` ``model:`` field) wins.
2. Otherwise the configured primary model.
3. Models whose provider has no credential in the environment are dropped.
4. Duplicate models are removed, order preserved.

``complete()`` walks the chain through ``call_with_fallback`` and records
actual spend on a :class:`~services.model_router.budgets.TaskBudget`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from services.model_router.budgets import TaskBudget, estimate_tokens, price_for
from services.model_router.fallback import (
    FallbackAttempt,
    NoProviderAvailableError,
    call_with_fallback,
)
from services.model_router.providers import (
    UnknownProviderError,
    credential_for,
    resolve_model,
)

TextCall = Callable[[str], Awaitable[str]]


@dataclass(frozen=True)
class RouteDecision:
    """Why the winning model was chosen - kept for logging and tests."""

    model: str
    source: str  # "agent-override" | "primary"
    considered: tuple[str, ...]  # chain before credential filtering
    dropped_no_credential: tuple[str, ...] = ()


def build_chain(
    primary: str,
    *,
    agent_model: str | None = None,
    fallbacks: Sequence[str] = (),
) -> tuple[str, ...]:
    """Ordered, de-duplicated chain of models with known providers.

    Raises :class:`UnknownProviderError` for misspelled providers - a typo
    should fail at configuration time, not silently at runtime.
    """
    ordered: list[str] = []
    if agent_model:
        ordered.append(agent_model)
    ordered.append(primary)
    ordered.extend(fallbacks)

    chain: list[str] = []
    for name in ordered:
        resolve_model(name)  # validates; raises UnknownProviderError on typo
        if name not in chain:
            chain.append(name)
    return tuple(chain)


def available_chain(chain: Sequence[str]) -> tuple[str, ...]:
    """Filter the chain down to models whose provider has a credential."""
    available: list[str] = []
    for name in chain:
        resolved = resolve_model(name)
        if credential_for(resolved.provider) is not None and name not in available:
            available.append(name)
    return tuple(available)


def route(
    primary: str,
    *,
    agent_model: str | None = None,
    fallbacks: Sequence[str] = (),
) -> RouteDecision:
    """Decide which model a call should use, applying credential filters."""
    chain = build_chain(primary, agent_model=agent_model, fallbacks=fallbacks)
    available = available_chain(chain)

    dropped = tuple(name for name in chain if name not in available)
    if not available:
        raise NoProviderAvailableError(
            "no model in the chain has credentials configured "
            f"(tried: {', '.join(chain)})"
        )

    source = "agent-override" if agent_model and available[0] == agent_model else "primary"
    return RouteDecision(
        model=available[0],
        source=source,
        considered=chain,
        dropped_no_credential=dropped,
    )


async def complete(
    call: TextCall,
    *,
    primary: str,
    agent_model: str | None = None,
    fallbacks: Sequence[str] = (),
    budget: TaskBudget | None = None,
    input_tokens: int = 0,
    expected_output_tokens: int = 0,
) -> tuple[str, RouteDecision, tuple[FallbackAttempt, ...]]:
    """Route a call through the fallback chain and bill the winning model.

    Returns ``(result, decision, attempts)`` where ``attempts`` are the
    failed tries before the winner (empty when the first choice worked).
    """
    decision = route(primary, agent_model=agent_model, fallbacks=fallbacks)
    chain = available_chain(decision.considered)

    if budget is not None:
        budget.preflight(decision.model, input_tokens, expected_output_tokens)

    result = await call_with_fallback(chain, call)

    if budget is not None:
        # Bill the model that actually answered; output tokens are estimated
        # from the returned text.
        budget.charge(
            result.model,
            _actual_cost(result.model, input_tokens, estimate_tokens(result.value)),
        )

    final = RouteDecision(
        model=result.model,
        source=(
            "agent-override"
            if agent_model and result.model == agent_model
            else "primary"
        ),
        considered=decision.considered,
        dropped_no_credential=decision.dropped_no_credential,
    )
    return result.value, final, result.attempts


def _actual_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Exact-basis cost for a completed call (unknown prices bill 0)."""
    try:
        price = price_for(model)
    except LookupError:
        return 0.0
    return (
        input_tokens * price.input_per_million + output_tokens * price.output_per_million
    ) / 1_000_000


__all__ = [
    "RouteDecision",
    "UnknownProviderError",
    "available_chain",
    "build_chain",
    "complete",
    "route",
]
