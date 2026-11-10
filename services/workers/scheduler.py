"""Durable background scheduling for recurring and delayed tasks.

The scheduler owns *when* work should run; the RQ worker owns *executing*
it. A :class:`TaskScheduler` stores :class:`Job` records through a small
:class:`ScheduleStore` interface - an in-memory dict for tests and a
Redis-backed hash for production. Nothing here imports Redis at module
level, so the whole scheduler is unit-testable without a server.

Retry policy: exponential backoff (2s, 4s, 8s, ...) capped at 5 minutes,
up to ``max_attempts`` total tries before the job is dropped.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

BACKOFF_BASE_SECONDS = 2.0
BACKOFF_CAP_SECONDS = 300.0
DEFAULT_MAX_ATTEMPTS = 3


class ScheduleError(RuntimeError):
    """Base class for scheduling failures."""


class RetriesExhaustedError(ScheduleError):
    """A job used up all of its attempts and has been dropped."""


def backoff_seconds(attempt: int) -> float:
    """Exponential backoff for the given 0-based attempt, capped at 5 min."""
    safe_attempt = max(0, attempt)
    return min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2**safe_attempt))


@dataclass(frozen=True)
class Job:
    """One scheduled execution of a task."""

    job_id: str
    task_id: str
    run_at: float
    attempts: int = 0
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    interval_seconds: float | None = None  # set for recurring jobs

    @property
    def recurring(self) -> bool:
        return self.interval_seconds is not None

    def to_json(self) -> str:
        return json.dumps(
            {
                "job_id": self.job_id,
                "task_id": self.task_id,
                "run_at": self.run_at,
                "attempts": self.attempts,
                "max_attempts": self.max_attempts,
                "interval_seconds": self.interval_seconds,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> Job:
        data = json.loads(raw)
        return cls(
            job_id=str(data["job_id"]),
            task_id=str(data["task_id"]),
            run_at=float(data["run_at"]),
            attempts=int(data["attempts"]),
            max_attempts=int(data["max_attempts"]),
            interval_seconds=(
                float(data["interval_seconds"])
                if data.get("interval_seconds") is not None
                else None
            ),
        )


class ScheduleStore(Protocol):
    """Persistence interface used by :class:`TaskScheduler`."""

    def put(self, job: Job) -> None: ...

    def get(self, job_id: str) -> Job | None: ...

    def delete(self, job_id: str) -> bool: ...

    def all(self) -> list[Job]: ...


class MemoryScheduleStore:
    """Dict-backed store for tests and single-process runs."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def put(self, job: Job) -> None:
        self._jobs[job.job_id] = job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def delete(self, job_id: str) -> bool:
        return self._jobs.pop(job_id, None) is not None

    def all(self) -> list[Job]:
        return list(self._jobs.values())


class RedisScheduleStore:
    """Redis hash-backed store (``workforce:schedule`` by default).

    Takes any client with ``hset/hget/hdel/hgetall`` (a real
    ``redis.Redis`` or a test double); no connection is opened here.
    """

    def __init__(self, client: Any, key: str = "workforce:schedule") -> None:
        self._client = client
        self._key = key

    def put(self, job: Job) -> None:
        self._client.hset(self._key, job.job_id, job.to_json())

    def get(self, job_id: str) -> Job | None:
        raw = self._client.hget(self._key, job_id)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return Job.from_json(str(raw))

    def delete(self, job_id: str) -> bool:
        return bool(self._client.hdel(self._key, job_id))

    def all(self) -> list[Job]:
        raw_jobs: dict = self._client.hgetall(self._key)
        jobs: list[Job] = []
        for value in raw_jobs.values():
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            jobs.append(Job.from_json(str(value)))
        return jobs


class TaskScheduler:
    """Schedule, complete, retry and cancel task jobs."""

    def __init__(
        self,
        store: ScheduleStore,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._store = store
        self._clock = clock

    def schedule(
        self,
        task_id: str,
        *,
        delay_seconds: float = 0.0,
        run_at: float | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> Job:
        """Schedule a one-shot run (``run_at`` wins over ``delay_seconds``)."""
        when = run_at if run_at is not None else self._clock() + delay_seconds
        job = Job(
            job_id=uuid.uuid4().hex,
            task_id=task_id,
            run_at=when,
            max_attempts=max_attempts,
        )
        self._store.put(job)
        return job

    def schedule_recurring(
        self,
        task_id: str,
        interval_seconds: float,
        *,
        first_delay_seconds: float = 0.0,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> Job:
        """Schedule a job that reschedules itself after every success."""
        if interval_seconds <= 0:
            raise ScheduleError("interval_seconds must be positive")
        job = Job(
            job_id=uuid.uuid4().hex,
            task_id=task_id,
            run_at=self._clock() + first_delay_seconds,
            max_attempts=max_attempts,
            interval_seconds=interval_seconds,
        )
        self._store.put(job)
        return job

    def due_jobs(self, *, now: float | None = None) -> list[Job]:
        """Jobs whose run time has arrived, soonest first."""
        moment = self._clock() if now is None else now
        return sorted(
            (job for job in self._store.all() if job.run_at <= moment),
            key=lambda job: job.run_at,
        )

    def complete(self, job_id: str) -> None:
        """Record success: drop one-shot jobs, advance recurring ones."""
        job = self._store.get(job_id)
        if job is None:
            raise ScheduleError(f"unknown job: {job_id}")
        if job.recurring:
            assert job.interval_seconds is not None
            self._store.put(
                Job(
                    job_id=job.job_id,
                    task_id=job.task_id,
                    run_at=self._clock() + job.interval_seconds,
                    attempts=0,
                    max_attempts=job.max_attempts,
                    interval_seconds=job.interval_seconds,
                )
            )
        else:
            self._store.delete(job_id)

    def retry(self, job_id: str) -> Job:
        """Record a failure: back off and reschedule, or drop the job."""
        job = self._store.get(job_id)
        if job is None:
            raise ScheduleError(f"unknown job: {job_id}")

        attempts = job.attempts + 1
        if attempts >= job.max_attempts:
            self._store.delete(job_id)
            raise RetriesExhaustedError(
                f"job {job_id} exhausted {job.max_attempts} attempts"
            )

        rescheduled = Job(
            job_id=job.job_id,
            task_id=job.task_id,
            run_at=self._clock() + backoff_seconds(job.attempts),
            attempts=attempts,
            max_attempts=job.max_attempts,
            interval_seconds=job.interval_seconds,
        )
        self._store.put(rescheduled)
        return rescheduled

    def cancel(self, job_id: str) -> bool:
        """Remove a job; False when it did not exist."""
        return self._store.delete(job_id)
