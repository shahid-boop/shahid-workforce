"""Redis/RQ worker entry point that executes enqueued tasks.

Flow of one job: load the task row -> mark it running -> run the
orchestrator graph -> persist ``completed`` (with the composed specialist
outputs) or ``failed`` (with the error). Re-running an already-completed
task is a no-op so redelivered jobs are safe.

The RQ/Redis imports live in :func:`main` so the execution logic can be
unit-tested (and type-checked) without a broker.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from database.connection import create_engine_for, create_session_factory
from database.repositories import task_repository
from services.orchestrator.state import StepOutput
from services.orchestrator.supervisor import AgentRunner

logger = logging.getLogger(__name__)

RUNNABLE_STATUSES = ("pending", "queued")
TERMINAL_STATUSES = ("completed", "failed", "cancelled")


class TaskExecutionError(RuntimeError):
    """The worker could not execute the requested task."""


def compose_result(outputs: Sequence[StepOutput]) -> str:
    """Render orchestrator outputs as one readable result string."""
    sections = [f"## {item['agent_id']}\n{item['output']}" for item in outputs]
    return "\n\n".join(sections)


async def execute_task_async(
    session: Session,
    task_id: str,
    runner: AgentRunner | None = None,
) -> str:
    """Execute one task inside ``session``; returns the final status."""
    task = task_repository.get_task(session, task_id)
    if task is None:
        raise TaskExecutionError(f"task not found: {task_id}")

    if task.status in TERMINAL_STATUSES:
        logger.info("task %s already %s, skipping", task_id, task.status)
        return task.status

    if task.status not in RUNNABLE_STATUSES:
        raise TaskExecutionError(
            f"task {task_id} is {task.status!r}; expected one of {RUNNABLE_STATUSES}"
        )

    task_repository.update_task(session, task_id, status="running")
    goal = task.description or task.title

    try:
        # Imported lazily: langgraph is only needed when actually running.
        from services.orchestrator.supervisor import run_task

        state = await run_task(task_id, goal, runner)
    except Exception as exc:
        logger.exception("task %s crashed", task_id)
        task_repository.update_task(
            session, task_id, status="failed", result=f"worker error: {exc}"
        )
        return "failed"

    if state["status"] == "failed":
        error = state.get("error") or "unknown orchestrator failure"
        task_repository.update_task(
            session, task_id, status="failed", result=error
        )
        return "failed"

    task_repository.update_task(
        session,
        task_id,
        status="completed",
        result=compose_result(state.get("outputs", [])),
    )
    return "completed"


def execute_task(
    session_factory: sessionmaker[Session],
    task_id: str,
    runner: AgentRunner | None = None,
) -> str:
    """Synchronous wrapper around :func:`execute_task_async` for RQ jobs."""
    session = session_factory()
    try:
        return asyncio.run(execute_task_async(session, task_id, runner))
    finally:
        session.close()


def run_job(task_id: str) -> str:
    """RQ entry point: build the session factory from the environment."""
    database_url = os.environ.get("WORKFORCE_DATABASE_URL")
    if not database_url:
        raise TaskExecutionError("WORKFORCE_DATABASE_URL is not set")
    factory = create_session_factory(create_engine_for(database_url))
    return execute_task(factory, task_id)


def enqueue_task(
    queue: Any,
    task_id: str,
    *,
    delay_seconds: float = 0,
) -> Any:
    """Put ``run_job`` on an RQ queue, optionally delayed."""
    if delay_seconds > 0:
        return queue.enqueue_in(timedelta(seconds=delay_seconds), run_job, task_id)
    return queue.enqueue(run_job, task_id)


def main() -> None:
    """Run the worker process: ``python -m services.workers.task_worker``."""
    from redis import Redis
    from rq import Queue, Worker

    redis_url = os.environ.get("WORKFORCE_REDIS_URL", "redis://127.0.0.1:6379/0")
    connection = Redis.from_url(redis_url)
    queue = Queue("workforce", connection=connection)
    logger.info("worker started on queue %r", queue.name)
    Worker([queue], connection=connection).work()


if __name__ == "__main__":
    main()
