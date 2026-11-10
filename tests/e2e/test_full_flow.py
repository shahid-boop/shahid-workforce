"""End-to-end flow: API -> database -> worker -> orchestrator -> result.

Requires langgraph (same guard as the orchestrator unit tests): skipped
locally where compiled dependencies cannot load, executed in CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

try:
    from langgraph.graph import END, START, StateGraph  # noqa: F401
except ImportError:
    pytest.skip(
        "langgraph compiled dependencies unavailable on this machine; CI runs them",
        allow_module_level=True,
    )

from database.connection import create_engine_for, create_session_factory
from database.repositories import task_repository
from services.api.config import Settings
from services.api.main import create_app
from services.orchestrator.supervisor import run_task
from services.workers.task_worker import compose_result, execute_task_async

API_KEY = "e2e-test-key"
GATES = ("code_reviewer", "qa_engineer")


def make_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        env="development",
        api_key=API_KEY,
        database_url=f"sqlite:///{tmp_path / 'e2e.db'}",
        cors_origins=(),
    )
    return TestClient(create_app(settings))


class SequenceRunner:
    """Fake agent runner producing one identifiable line per specialist."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[str] = []
        self.fail_on = fail_on

    async def __call__(self, definition, ctx) -> str:  # type: ignore[no-untyped-def]
        self.calls.append(definition.id)
        if definition.id == self.fail_on:
            raise RuntimeError("simulated specialist failure")
        return f"[{definition.id}] handled: {ctx.input[:40]}"


# ---------------------------------------------------------------- full flow


def test_full_flow_create_execute_complete(tmp_path: Path) -> None:
    """POST /tasks -> worker execution -> status completed with outputs."""
    with make_client(tmp_path) as client:
        created = client.post(
            "/tasks",
            json={"title": "build landing page", "description": "responsive"},
            headers={"X-API-Key": API_KEY},
        )
        assert created.status_code == 201
        task_id = created.json()["id"]
        assert created.json()["status"] == "pending"

        # Worker claims the pending task and runs the orchestrator.
        settings = client.app.state.settings  # type: ignore[attr-defined]
        engine = create_engine_for(settings.database_url)
        factory = create_session_factory(engine)
        session = factory()
        try:
            runner = SequenceRunner()
            status = __import__("asyncio").run(
                execute_task_async(session, task_id, runner)
            )
        finally:
            session.close()
            engine.dispose()

        assert status == "completed"
        # The plan must have run specialists and both quality gates.
        assert len(runner.calls) >= 3
        assert runner.calls[-2:] == list(GATES)

        # API reflects the finished task with a composed result.
        fetched = client.get(
            f"/tasks/{task_id}", headers={"X-API-Key": API_KEY}
        )
        body = fetched.json()
        assert body["status"] == "completed"
        assert "## code_reviewer" in body["result"]
        assert "## qa_engineer" in body["result"]


def test_full_flow_failed_specialist_marks_task_failed(tmp_path: Path) -> None:
    """A failing specialist stops the run and the task ends failed."""
    with make_client(tmp_path) as client:
        created = client.post(
            "/tasks",
            json={"title": "doomed task"},
            headers={"X-API-Key": API_KEY},
        )
        task_id = created.json()["id"]

        settings = client.app.state.settings  # type: ignore[attr-defined]
        engine = create_engine_for(settings.database_url)
        factory = create_session_factory(engine)
        session = factory()
        try:
            runner = SequenceRunner(fail_on="code_reviewer")
            status = __import__("asyncio").run(
                execute_task_async(session, task_id, runner)
            )
            task = task_repository.get_task(session, task_id)
        finally:
            session.close()
            engine.dispose()

        assert status == "failed"
        assert task is not None
        assert task.status == "failed"
        assert "code_reviewer" in (task.result or "")
        # qa_engineer must not run after a failed gate
        assert "qa_engineer" not in runner.calls


def test_full_flow_is_idempotent_for_completed_tasks(tmp_path: Path) -> None:
    """Re-delivering a finished job must not re-run the plan."""
    with make_client(tmp_path) as client:
        created = client.post(
            "/tasks",
            json={"title": "once only"},
            headers={"X-API-Key": API_KEY},
        )
        task_id = created.json()["id"]

        settings = client.app.state.settings  # type: ignore[attr-defined]
        engine = create_engine_for(settings.database_url)
        factory = create_session_factory(engine)
        session = factory()
        try:
            first_runner = SequenceRunner()
            assert (
                __import__("asyncio").run(
                    execute_task_async(session, task_id, first_runner)
                )
                == "completed"
            )
            second_runner = SequenceRunner()
            status = __import__("asyncio").run(
                execute_task_async(session, task_id, second_runner)
            )
        finally:
            session.close()
            engine.dispose()

        assert status == "completed"
        assert second_runner.calls == [], "completed task must not re-execute"


# ------------------------------------------------------------ plan guarantees


def test_every_plan_ends_with_both_gates() -> None:
    """Routing invariant: review + QA gates always appended, in order."""
    from services.orchestrator.routing import build_plan

    for goal in (
        "fix the login bug",
        "design a database schema",
        "write a marketing landing page",
        "research competitor pricing",
        "ship a release",
    ):
        plan = build_plan(goal)
        assert plan[-2:] == list(GATES), goal


def test_run_task_returns_composed_outputs() -> None:
    """Direct orchestrator run exposes one output per planned step."""
    import asyncio

    runner = SequenceRunner()
    state = asyncio.run(run_task("task-e2e", "build the api", runner))
    assert state["status"] == "completed"
    assert [item["agent_id"] for item in state["outputs"]] == runner.calls
    rendered = compose_result(state["outputs"])
    assert rendered.count("## ") == len(runner.calls)
