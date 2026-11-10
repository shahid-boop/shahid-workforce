"""Tests for the RQ task worker: status transitions and job entry points.

Tests that execute the real orchestrator graph need langgraph; they are
skipped on machines whose compiled dependencies are blocked and run in CI.
The rest (validation, terminal-state handling, queue helpers) run anywhere.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

from agents.base_agent import AgentContext
from agents.registry import AgentDefinition
from database.connection import create_engine_for, create_session_factory
from database.models import Base
from database.repositories import task_repository
from services.workers.task_worker import (
    TaskExecutionError,
    compose_result,
    enqueue_task,
    execute_task_async,
    run_job,
)

try:
    import langgraph.graph  # noqa: F401

    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False

graph_test = pytest.mark.skipif(
    not HAS_LANGGRAPH,
    reason="langgraph compiled dependencies unavailable on this machine; CI runs them",
)


def make_factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine_for(f"sqlite:///{tmp_path / 'worker.db'}")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


class RecordingRunner:
    """Fake agent runner producing deterministic outputs."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []

    async def __call__(self, definition: AgentDefinition, ctx: AgentContext) -> str:
        self.calls.append(definition.id)
        if self.fail:
            raise RuntimeError("boom")
        return f"out:{definition.id}"


# --- validation (no graph needed) -------------------------------------------


def test_execute_task_unknown_id_raises(tmp_path: Path) -> None:
    factory = make_factory(tmp_path)
    session = factory()
    try:
        with pytest.raises(TaskExecutionError, match="task not found"):
            asyncio.run(execute_task_async(session, "ghost"))
    finally:
        session.close()


def test_execute_task_rejects_running_status(tmp_path: Path) -> None:
    factory = make_factory(tmp_path)
    session = factory()
    try:
        task = task_repository.create_task(session, title="in flight")
        task_repository.update_task(session, task.id, status="running")
        with pytest.raises(TaskExecutionError, match="expected one of"):
            asyncio.run(execute_task_async(session, task.id))
    finally:
        session.close()


def test_execute_task_skips_completed_task(tmp_path: Path) -> None:
    factory = make_factory(tmp_path)
    session = factory()
    try:
        task = task_repository.create_task(session, title="done already")
        task_repository.update_task(
            session, task.id, status="completed", result="prior output"
        )

        runner = RecordingRunner()
        status = asyncio.run(execute_task_async(session, task.id, runner))

        assert status == "completed"
        assert runner.calls == []  # never re-executed
        refreshed = task_repository.get_task(session, task.id)
        assert refreshed is not None
        assert refreshed.result == "prior output"
    finally:
        session.close()


def test_execute_task_skips_cancelled_task(tmp_path: Path) -> None:
    factory = make_factory(tmp_path)
    session = factory()
    try:
        task = task_repository.create_task(session, title="cancelled")
        task_repository.update_task(session, task.id, status="cancelled")

        status = asyncio.run(execute_task_async(session, task.id, RecordingRunner()))
        assert status == "cancelled"
    finally:
        session.close()


# --- compose_result ---------------------------------------------------------


def test_compose_result_renders_sections() -> None:
    rendered = compose_result(
        [
            {"agent_id": "system_architect", "output": "plan text"},
            {"agent_id": "qa_engineer", "output": "qa text"},
        ]
    )
    assert rendered == "## system_architect\nplan text\n\n## qa_engineer\nqa text"


def test_compose_result_empty_is_empty_string() -> None:
    assert compose_result([]) == ""


# --- execution through the graph (CI) ---------------------------------------


@graph_test
def test_execute_task_marks_completed_with_outputs(tmp_path: Path) -> None:
    factory = make_factory(tmp_path)
    session = factory()
    try:
        task = task_repository.create_task(
            session, title="Build the React frontend", description=None
        )
        runner = RecordingRunner()

        status = asyncio.run(execute_task_async(session, task.id, runner))

        assert status == "completed"
        refreshed = task_repository.get_task(session, task.id)
        assert refreshed is not None
        assert refreshed.status == "completed"
        assert refreshed.result is not None
        assert "## code_reviewer" in refreshed.result
        assert "out:qa_engineer" in refreshed.result
        # every plan step executed exactly once
        assert len(runner.calls) == len(set(runner.calls))
        assert runner.calls[-2:] == ["code_reviewer", "qa_engineer"]
    finally:
        session.close()


@graph_test
def test_execute_task_marks_failed_when_runner_raises(tmp_path: Path) -> None:
    factory = make_factory(tmp_path)
    session = factory()
    try:
        task = task_repository.create_task(session, title="review this diff")
        runner = RecordingRunner(fail=True)

        status = asyncio.run(execute_task_async(session, task.id, runner))

        assert status == "failed"
        refreshed = task_repository.get_task(session, task.id)
        assert refreshed is not None
        assert refreshed.status == "failed"
        assert refreshed.result is not None
        assert "boom" in refreshed.result
    finally:
        session.close()


@graph_test
def test_execute_task_marks_failed_when_crash_is_raised(tmp_path: Path) -> None:
    factory = make_factory(tmp_path)
    session = factory()
    try:
        task = task_repository.create_task(session, title="anything")

        async def exploding_runner(
            definition: AgentDefinition, ctx: AgentContext
        ) -> str:
            raise RuntimeError("total meltdown")

        status = asyncio.run(execute_task_async(session, task.id, exploding_runner))

        assert status == "failed"
        refreshed = task_repository.get_task(session, task.id)
        assert refreshed is not None
        assert refreshed.status == "failed"
        assert refreshed.result is not None
        assert "total meltdown" in refreshed.result
    finally:
        session.close()


# --- RQ entry points --------------------------------------------------------


def test_run_job_without_database_url_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKFORCE_DATABASE_URL", raising=False)
    with pytest.raises(TaskExecutionError, match="WORKFORCE_DATABASE_URL"):
        run_job("t-1")


def test_run_job_executes_against_configured_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = f"sqlite:///{tmp_path / 'job.db'}"
    engine = create_engine_for(database_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    session = factory()
    try:
        task = task_repository.create_task(session, title="queued job")
        task_repository.update_task(session, task.id, status="cancelled")
    finally:
        session.close()

    monkeypatch.setenv("WORKFORCE_DATABASE_URL", database_url)
    # terminal status -> run_job resolves the DB and skips without a graph call
    assert run_job(task.id) == "cancelled"


class FakeQueue:
    """Records enqueues without a broker."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def enqueue(self, func: Any, *args: Any) -> str:
        self.calls.append(("now", (func, *args)))
        return "job-immediate"

    def enqueue_in(self, delay: Any, func: Any, *args: Any) -> str:
        self.calls.append(("delayed", (delay, func, *args)))
        return "job-delayed"


def test_enqueue_task_immediate() -> None:
    queue = FakeQueue()
    job_id = enqueue_task(queue, "t-1")
    assert job_id == "job-immediate"
    kind, payload = queue.calls[0]
    assert kind == "now"
    assert payload[0] is run_job
    assert payload[1] == "t-1"


def test_enqueue_task_delayed() -> None:
    queue = FakeQueue()
    job_id = enqueue_task(queue, "t-1", delay_seconds=45)
    assert job_id == "job-delayed"
    kind, payload = queue.calls[0]
    assert kind == "delayed"
    assert payload[0].total_seconds() == 45
    assert payload[1] is run_job
    assert payload[2] == "t-1"
