"""Tests for supervised graph execution.

Requires langgraph. On machines where its compiled dependencies cannot load,
these tests are skipped locally and run in CI instead.
"""

from __future__ import annotations

import asyncio

import pytest

try:
    from langgraph.graph import END, START, StateGraph  # noqa: F401
except ImportError:
    pytest.skip(
        "langgraph compiled dependencies unavailable on this machine; CI runs them",
        allow_module_level=True,
    )

from agents.base_agent import AgentContext
from agents.registry import AgentDefinition
from services.orchestrator.supervisor import run_task

GATES = ["code_reviewer", "qa_engineer"]


class RecordingRunner:
    """Fake agent runner that records calls and can fail on one agent id."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.calls: list[tuple[str, AgentContext]] = []

    async def __call__(self, definition: AgentDefinition, ctx: AgentContext) -> str:
        self.calls.append((definition.id, ctx))
        if definition.id == self.fail_on:
            raise RuntimeError("boom")
        return f"out:{definition.id}"


def test_run_task_completes_and_records_outputs_in_plan_order() -> None:
    runner = RecordingRunner()
    state = asyncio.run(run_task("t-1", "Build the React frontend", runner))

    assert state["status"] == "completed"
    assert state["error"] is None
    assert state["plan"][-2:] == GATES
    assert [item["agent_id"] for item in state["outputs"]] == state["plan"]
    assert state["step_index"] == len(state["plan"])


def test_each_step_receives_prior_successful_outputs() -> None:
    runner = RecordingRunner()
    state = asyncio.run(run_task("t-2", "design the SQL schema", runner))

    contexts = [ctx for _, ctx in runner.calls]
    assert contexts[0].prior_outputs == ()
    assert len(contexts[1].prior_outputs) == 1
    assert len(contexts[-1].prior_outputs) == len(state["plan"]) - 1
    assert contexts[-1].prior_outputs[0].startswith("out:")


def test_failing_step_marks_run_failed_and_stops() -> None:
    runner = RecordingRunner(fail_on="code_reviewer")
    state = asyncio.run(run_task("t-3", "review this diff", runner))

    assert state["status"] == "failed"
    assert state["error"] is not None
    assert "code_reviewer" in state["error"]
    assert "boom" in state["error"]
    executed = [agent_id for agent_id, _ in runner.calls]
    assert "code_reviewer" in executed
    assert "qa_engineer" not in executed  # gate after failure never runs
    assert state["step_index"] == state["plan"].index("code_reviewer") + 1


def test_default_runner_produces_template_output() -> None:
    state = asyncio.run(run_task("t-4", "write the documentation readme"))
    assert state["status"] == "completed"
    first_output = state["outputs"][0]["output"]
    assert "# Documentation Engineer" in first_output


def test_run_task_uses_goal_as_agent_input() -> None:
    runner = RecordingRunner()
    asyncio.run(run_task("t-5", "evaluate redis vs rabbitmq", runner))
    assert all(ctx.input == "evaluate redis vs rabbitmq" for _, ctx in runner.calls)
    assert all(ctx.task_id == "t-5" for _, ctx in runner.calls)
