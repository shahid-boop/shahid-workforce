"""Shared tool interface and registry.

Every tool is allowlisted by name and invoked with explicit arguments -
never by interpolating agent text into a shell. Tools raise
:class:`ToolError` for expected failures so callers can report them
without tracebacks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

MAX_OUTPUT_CHARS = 20_000


class ToolError(RuntimeError):
    """An expected, reportable tool failure."""


class ToolNotFoundError(ToolError):
    """The requested tool name is not registered."""


@dataclass(frozen=True)
class ToolResult:
    """Outcome of one tool invocation."""

    tool: str
    ok: bool
    output: str
    data: dict[str, Any] = field(default_factory=dict)


class BaseTool(ABC):
    """Interface every tool implements."""

    name: ClassVar[str]
    description: ClassVar[str]

    @abstractmethod
    def run(self, **kwargs: Any) -> ToolResult:
        """Execute the tool; raise :class:`ToolError` on expected failures."""
        raise NotImplementedError


REGISTRY: dict[str, type[BaseTool]] = {}


def register(cls: type[BaseTool]) -> type[BaseTool]:
    """Class decorator adding a tool to the allowlist registry."""
    tool_name = getattr(cls, "name", "")
    if not tool_name:
        raise ToolError(f"{cls.__name__} must define a non-empty 'name'")
    if tool_name in REGISTRY and REGISTRY[tool_name] is not cls:
        raise ToolError(f"duplicate tool name: {tool_name}")
    REGISTRY[tool_name] = cls
    return cls


def tool_names() -> tuple[str, ...]:
    """All registered tool names, sorted."""
    return tuple(sorted(REGISTRY))


def tool_specs() -> list[dict[str, str]]:
    """Name/description pairs for prompts and API responses."""
    return [
        {"name": cls.name, "description": cls.description}
        for _, cls in sorted(REGISTRY.items())
    ]


def create_tool(name: str, **config: Any) -> BaseTool:
    """Instantiate a registered tool with constructor config."""
    cls = REGISTRY.get(name)
    if cls is None:
        raise ToolNotFoundError(
            f"unknown tool: {name!r} (available: {', '.join(tool_names())})"
        )
    return cls(**config)


def truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    """Cap huge outputs so one tool result cannot flood the context."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"


def scrub(text: str, secret: str | None) -> str:
    """Remove a secret from text before it reaches logs or callers."""
    if secret and secret in text:
        return text.replace(secret, "***")
    return text


def status_of(data: Mapping[str, Any]) -> bool:
    """Convenience for tools whose result carries a success flag."""
    return bool(data.get("ok", True))
