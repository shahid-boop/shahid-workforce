"""Shared orchestration state passed between graph nodes."""

from __future__ import annotations

from typing import TypedDict


class StepOutput(TypedDict):
    """Result of one executed specialist step."""

    agent_id: str
    output: str


class OrchestratorState(TypedDict, total=False):
    """State travelling through the orchestrator graph."""

    task_id: str
    goal: str
    plan: list[str]
    step_index: int
    outputs: list[StepOutput]
    status: str
    error: str | None


def initial_state(task_id: str, goal: str) -> OrchestratorState:
    """Return a fully initialised state for a new run."""
    return {
        "task_id": task_id,
        "goal": goal,
        "plan": [],
        "step_index": 0,
        "outputs": [],
        "status": "pending",
        "error": None,
    }
