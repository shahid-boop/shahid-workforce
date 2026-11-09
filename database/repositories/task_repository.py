"""CRUD operations for tasks."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models.task import Task


def create_task(session: Session, *, title: str, description: str | None = None) -> Task:
    """Persist a new task in pending state."""
    task = Task(title=title, description=description)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def get_task(session: Session, task_id: str) -> Task | None:
    """Return one task by id, or None."""
    return session.get(Task, task_id)


def list_tasks(
    session: Session, *, status: str | None = None, limit: int = 50
) -> list[Task]:
    """Return tasks newest-first, optionally filtered by status."""
    stmt = select(Task).order_by(Task.created_at.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(Task.status == status)
    return list(session.scalars(stmt))


def update_task(
    session: Session, task_id: str, *, status: str | None = None, result: str | None = None
) -> Task | None:
    """Update mutable fields of a task; returns None when it does not exist."""
    task = session.get(Task, task_id)
    if task is None:
        return None
    if status is not None:
        task.status = status
    if result is not None:
        task.result = result
    session.commit()
    session.refresh(task)
    return task


def delete_task(session: Session, task_id: str) -> bool:
    """Delete a task; returns False when it does not exist."""
    task = session.get(Task, task_id)
    if task is None:
        return False
    session.delete(task)
    session.commit()
    return True
