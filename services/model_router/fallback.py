"""Fallback behaviour when the primary provider fails or is unavailable.

The chain is an ordered list of model names. A call walks it from the
front: transport/API errors and rate limits advance to the next model,
while caller errors (bad request shape) are raised immediately because a
different provider would reject them too.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    """A provider failed in a way that may be transient (5xx, rate limit)."""


class ProviderRejectedError(ProviderError):
    """The provider understood the request but refused it (4xx)."""


class NoProviderAvailableError(RuntimeError):
    """Every model in the fallback chain failed."""


@dataclass(frozen=True)
class FallbackAttempt:
    """One failed attempt recorded on the way to success (or exhaustion)."""

    model: str
    error: str


@dataclass(frozen=True)
class FallbackResult:
    """Outcome of a successful call, including which models were tried."""

    model: str
    value: str
    attempts: tuple[FallbackAttempt, ...] = field(default_factory=tuple)


# Errors that are worth retrying on a different provider.
RETRYABLE_ERRORS = (ProviderError, TimeoutError, ConnectionError)
# Errors that mean the request itself is bad; do not rotate providers.
FATAL_ERRORS = (ProviderRejectedError, ValueError, TypeError)


async def call_with_fallback(
    chain: Sequence[str],
    call: Callable[[str], Awaitable[str]],
    *,
    is_retryable: Callable[[Exception], bool] | None = None,
) -> FallbackResult:
    """Run ``call`` against each model in ``chain`` until one succeeds.

    ``call`` receives a model name and returns the text result. Exceptions
    matching ``FATAL_ERRORS`` abort immediately; everything else advances
    the chain and is recorded as an attempt.
    """
    if not chain:
        raise NoProviderAvailableError("empty fallback chain")

    retryable = is_retryable or _default_is_retryable
    attempts: list[FallbackAttempt] = []

    for model in chain:
        try:
            value = await call(model)
        except FATAL_ERRORS:
            raise
        except Exception as exc:
            if not retryable(exc):
                raise
            logger.warning("model %s failed, trying next: %s", model, exc)
            attempts.append(FallbackAttempt(model=model, error=str(exc)))
            continue
        return FallbackResult(
            model=model, value=value, attempts=tuple(attempts)
        )

    detail = "; ".join(f"{a.model}: {a.error}" for a in attempts)
    raise NoProviderAvailableError(f"all models failed: {detail}")


def _default_is_retryable(exc: Exception) -> bool:
    """Default retry policy: transient provider errors and timeouts."""
    return isinstance(exc, RETRYABLE_ERRORS)
