"""Estimate-based per-task spend ceiling and preflight pricing checks.

All numbers here are *estimates*: tokens are approximated from text length
and prices come from a static table. The router uses them to refuse calls
that would obviously exceed a task's ceiling; exact billing is the
provider's job, not ours.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class BudgetExceededError(RuntimeError):
    """Raised when a call would push a task past its spend ceiling."""


class UnknownPriceError(LookupError):
    """Raised when a model has no price entry and exact pricing is required."""


@dataclass(frozen=True)
class ModelPrice:
    """USD price per million tokens."""

    input_per_million: float
    output_per_million: float


# Static price table (USD per 1M tokens). Update when providers reprice.
PRICES: dict[str, ModelPrice] = {
    "openai/gpt-4o-mini": ModelPrice(0.15, 0.60),
    "openai/gpt-4o": ModelPrice(2.50, 10.00),
    "anthropic/claude-3-5-haiku": ModelPrice(0.80, 4.00),
    "anthropic/claude-3-5-sonnet": ModelPrice(3.00, 15.00),
    "google/gemini-2.0-flash": ModelPrice(0.10, 0.40),
    "groq/llama-3.3-70b-versatile": ModelPrice(0.59, 0.79),
    "mistral/mistral-small-latest": ModelPrice(0.10, 0.30),
}

# Rough chars-per-token ratio used for estimates.
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Approximate token count from text length (at least 1 for non-empty)."""
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


def estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    """Estimate total tokens for a chat message list."""
    return sum(estimate_tokens(str(message.get("content", ""))) for message in messages)


def price_for(model: str, *, default: ModelPrice | None = None) -> ModelPrice:
    """Return the price for ``model``; unknown models use ``default`` if given."""
    price = PRICES.get(model)
    if price is not None:
        return price
    if default is not None:
        return default
    raise UnknownPriceError(f"no price known for model {model!r}")


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimated USD cost of one call against the static price table."""
    price = price_for(model)
    return (
        input_tokens * price.input_per_million
        + output_tokens * price.output_per_million
    ) / 1_000_000


@dataclass
class TaskBudget:
    """Spend ceiling for one task run."""

    ceiling_usd: float
    spent_usd: float = 0.0
    charges: list[tuple[str, float]] = field(default_factory=list)

    @property
    def remaining_usd(self) -> float:
        return self.ceiling_usd - self.spent_usd

    def preflight(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Return the estimate, raising if it would exceed the ceiling.

        Unknown prices are treated as free here so an unpriced model is
        never blocked outright - only *known* costs count against a ceiling.
        """
        try:
            cost = estimate_cost_usd(model, input_tokens, output_tokens)
        except UnknownPriceError:
            return 0.0
        if self.spent_usd + cost > self.ceiling_usd:
            raise BudgetExceededError(
                f"estimated ${cost:.6f} would exceed task ceiling "
                f"(${self.spent_usd:.6f} spent of ${self.ceiling_usd:.6f})"
            )
        return cost

    def charge(self, model: str, actual_usd: float) -> None:
        """Record actual spend after a completed call."""
        self.spent_usd += actual_usd
        self.charges.append((model, actual_usd))
