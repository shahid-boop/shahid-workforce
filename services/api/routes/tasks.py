"""Task CRUD endpoints (private: X-API-Key required).

In development (``Settings.auto_run``) a created task is executed inline
right after the response is sent - no Redis, no worker process - so the
default ``python -m uvicorn`` flow actually runs tasks end-to-end. In
production the task stays ``pending`` for the RQ worker to pick up.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from sqlalchemy.orm import Session

from database.repositories import task_repository
from services.api.auth.api_key import require_api_key
from services.api.schemas import TaskCreate, TaskList, TaskOut, TaskUpdate
from services.workers.task_worker import execute_task_async

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
    dependencies=[Depends(require_api_key)],
)


def get_session(request: Request) -> Iterator[Session]:
    """Yield a database session per request and close it afterwards."""
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def run_inline(session_factory, task_id: str) -> None:
    """Execute a task in-process after the response (dev auto-run).

    Runs in FastAPI's threadpool (``BackgroundTasks`` with a sync callable),
    so a fresh event loop via ``asyncio.run`` is safe. Failures are logged
    and recorded on the task itself by ``execute_task_async`` - they never
    surface to the already-sent HTTP response.
    """
    session = session_factory()
    try:
        asyncio.run(execute_task_async(session, task_id))
    except Exception:
        logger.exception("inline execution failed for task %s", task_id)
    finally:
        session.close()


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> TaskOut:
    """Create a task in pending state (auto-run executes it right after)."""
    task = task_repository.create_task(
        session, title=payload.title, description=payload.description
    )
    settings = request.app.state.settings
    if settings.auto_run:
        background_tasks.add_task(
            run_inline, request.app.state.session_factory, task.id
        )
    return TaskOut.model_validate(task)


@router.get("", response_model=TaskList)
def list_tasks(
    task_status: str | None = Query(default=None, alias="status"),
    limit: int = 50,
    session: Session = Depends(get_session),
) -> TaskList:
    """List tasks newest-first; optionally filter by status."""
    if limit < 1 or limit > 200:
        raise HTTPException(
            status_code=422,
            detail="limit must be between 1 and 200",
        )
    if task_status is not None and task_status not in (
        "pending",
        "queued",
        "running",
        "completed",
        "failed",
        "cancelled",
    ):
        raise HTTPException(
            status_code=422,
            detail="unknown status filter",
        )
    tasks = task_repository.list_tasks(session, status=task_status, limit=limit)
    items = [TaskOut.model_validate(task) for task in tasks]
    return TaskList(items=items, count=len(items))


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str, session: Session = Depends(get_session)) -> TaskOut:
    """Fetch a single task by id."""
    task = task_repository.get_task(session, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="task not found"
        )
    return TaskOut.model_validate(task)


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: str,
    payload: TaskUpdate,
    session: Session = Depends(get_session),
) -> TaskOut:
    """Update task status and/or result."""
    if payload.status is None and payload.result is None:
        raise HTTPException(
            status_code=422,
            detail="nothing to update",
        )
    task = task_repository.update_task(
        session, task_id, status=payload.status, result=payload.result
    )
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="task not found"
        )
    return TaskOut.model_validate(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, session: Session = Depends(get_session)) -> None:
    """Delete a task."""
    if not task_repository.delete_task(session, task_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="task not found"
        )
