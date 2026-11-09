"""Common agent interface shared by all specialists."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentContext:
    task_id: str
    input: str
    prior_outputs: tuple[str, ...] = ()


class BaseAgent:
    """Base class every specialist implements."""

    agent_id: str = ""

    async def run(self, ctx: AgentContext) -> str:
        raise NotImplementedError