"""Common agent interface shared by all specialists.

``TemplateAgent`` assembles the final prompt without calling a model. It is
the execution placeholder until the model router step wires real providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from agents.registry import AgentDefinition


@dataclass(frozen=True)
class AgentContext:
    """Input handed to an agent for one task step."""

    task_id: str
    input: str
    prior_outputs: tuple[str, ...] = ()


class BaseAgent(ABC):
    """Base class every specialist implements."""

    def __init__(self, definition: AgentDefinition) -> None:
        self.definition = definition

    @property
    def agent_id(self) -> str:
        return self.definition.id

    def build_messages(self, ctx: AgentContext) -> list[dict[str, str]]:
        """Return chat messages: system prompt plus the task with context."""
        sections = [f"Task ID: {ctx.task_id}", ctx.input]
        if ctx.prior_outputs:
            numbered = "\n".join(
                f"{position}. {output}"
                for position, output in enumerate(ctx.prior_outputs, start=1)
            )
            sections.append(f"Previous specialist outputs:\n{numbered}")
        return [
            {"role": "system", "content": self.definition.prompt},
            {"role": "user", "content": "\n\n".join(sections)},
        ]

    @abstractmethod
    async def run(self, ctx: AgentContext) -> str:
        """Execute this agent for the given context and return its output."""
        raise NotImplementedError


class TemplateAgent(BaseAgent):
    """Assemble the full prompt as output; no model is called yet."""

    async def run(self, ctx: AgentContext) -> str:
        messages = self.build_messages(ctx)
        return "\n\n".join(message["content"] for message in messages)


def make_agent(agent_id: str) -> BaseAgent:
    """Build the default agent implementation for a configured id."""
    from agents.registry import get_agent

    return TemplateAgent(get_agent(agent_id))
