"""Top-level task supervision: plan, dispatch specialists, collect results.

Specialists run sequentially; each step receives all prior successful outputs
as reviewable context. A failing specialist stops the run and marks it failed.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from agents.base_agent import AgentContext, TemplateAgent
from agents.registry import AgentDefinition, get_agent
from services.orchestrator.routing import build_plan
from services.orchestrator.state import OrchestratorState, initial_state

logger = logging.getLogger(__name__)

AgentRunner = Callable[[AgentDefinition, AgentContext], Awaitable[str]]


async def default_agent_runner(
    definition: AgentDefinition, ctx: AgentContext
) -> str:
    """Execute an agent through the configured LLM chain.

    Falls back to the template placeholder when no provider credential is
    configured, so the orchestrator keeps working before any key exists.
    """
    from services.model_router.llm import complete_messages

    agent = TemplateAgent(definition)
    text = await complete_messages(
        agent.build_messages(ctx),
        agent_model=definition.model,
    )
    if text is None:
        return await agent.run(ctx)
    return text


class StepFailed(RuntimeError):
    """Raised when a specialist step cannot be completed."""


def apply_plan(state: OrchestratorState) -> OrchestratorState:
    """Node: compute the plan for the goal and mark the run as running."""
    state["plan"] = build_plan(state["goal"])
    state["status"] = "running"
    logger.info("task %s plan: %s", state["task_id"], " -> ".join(state["plan"]))
    return state


async def run_next_step(
    state: OrchestratorState, runner: AgentRunner
) -> OrchestratorState:
    """Execute the specialist at ``step_index`` and advance the cursor."""
    plan = state["plan"]
    index = state["step_index"]
    if index >= len(plan):
        return state

    agent_id = plan[index]
    definition = get_agent(agent_id)
    prior_outputs = tuple(
        item["output"] for item in state.get("outputs", [])
    )
    ctx = AgentContext(
        task_id=state["task_id"],
        input=state["goal"],
        prior_outputs=prior_outputs,
    )

    try:
        output = await runner(definition, ctx)
    except Exception as exc:
        logger.warning("task %s step %s failed: %s", state["task_id"], agent_id, exc)
        state["status"] = "failed"
        state["error"] = f"{agent_id}: {exc}"
        state["step_index"] = index + 1
        return state

    outputs = list(state.get("outputs", []))
    outputs.append({"agent_id": agent_id, "output": output})
    state["outputs"] = outputs
    state["step_index"] = index + 1
    return state


def finish(state: OrchestratorState) -> OrchestratorState:
    """Node: mark a fully executed plan as completed."""
    if state["status"] != "failed":
        state["status"] = "completed"
    return state


async def run_task(
    task_id: str,
    goal: str,
    runner: AgentRunner | None = None,
) -> OrchestratorState:
    """Plan and execute a goal through the compiled orchestrator graph."""
    from services.orchestrator.graph import build_graph

    graph = build_graph(runner or default_agent_runner)
    result = await graph.ainvoke(initial_state(task_id, goal))
    return dict(result)  # type: ignore[return-value]
