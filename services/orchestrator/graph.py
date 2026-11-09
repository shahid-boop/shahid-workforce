"""LangGraph task graph: plan -> sequential specialist steps -> finish.

The two mandatory gates (code review, QA) are already the last entries of the
plan produced by ``routing.build_plan``; the executor simply walks the plan
and stops early when a step fails.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from services.orchestrator.state import OrchestratorState
from services.orchestrator.supervisor import (
    AgentRunner,
    apply_plan,
    finish,
    run_next_step,
)


def _next(state: OrchestratorState) -> str:
    """Conditional edge: keep stepping, finish, or stop on failure."""
    if state.get("status") == "failed":
        return "end"
    if state["step_index"] < len(state["plan"]):
        return "step"
    return "finish"


def build_graph(runner: AgentRunner) -> Any:
    """Compile the orchestrator graph bound to a specific agent runner."""

    async def step(state: OrchestratorState) -> OrchestratorState:
        # Must be an async def (not a lambda returning a coroutine) so langgraph
        # awaits it instead of treating the coroutine as the node's return value.
        return await run_next_step(state, runner)

    graph = StateGraph(OrchestratorState)

    graph.add_node("plan", apply_plan)
    graph.add_node("step", step)
    graph.add_node("finish", finish)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "step")
    graph.add_conditional_edges(
        "step",
        _next,
        {"step": "step", "finish": "finish", "end": END},
    )
    graph.add_edge("finish", END)
    return graph.compile()
