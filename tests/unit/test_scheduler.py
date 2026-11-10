"""Tests for the durable scheduler: jobs, due times, retries, recurrence."""

from __future__ import annotations

import pytest

from services.workers.scheduler import (
    BACKOFF_CAP_SECONDS,
    Job,
    MemoryScheduleStore,
    RedisScheduleStore,
    RetriesExhaustedError,
    ScheduleError,
    TaskScheduler,
    backoff_seconds,
)

# --- backoff ----------------------------------------------------------------


def test_backoff_doubles_per_attempt() -> None:
    assert backoff_seconds(0) == 2.0
    assert backoff_seconds(1) == 4.0
    assert backoff_seconds(2) == 8.0


def test_backoff_is_capped() -> None:
    assert backoff_seconds(50) == BACKOFF_CAP_SECONDS


def test_backoff_negative_attempt_treated_as_zero() -> None:
    assert backoff_seconds(-3) == 2.0


# --- job serialization ------------------------------------------------------


def test_job_json_roundtrip() -> None:
    job = Job(job_id="abc", task_id="t-1", run_at=1700000000.5, attempts=2)
    assert Job.from_json(job.to_json()) == job


def test_job_json_roundtrip_recurring() -> None:
    job = Job(
        job_id="abc",
        task_id="t-1",
        run_at=1700000000.5,
        interval_seconds=3600.0,
    )
    restored = Job.from_json(job.to_json())
    assert restored.recurring is True
    assert restored.interval_seconds == 3600.0


# --- one-shot scheduling ----------------------------------------------------


def test_schedule_uses_clock_plus_delay() -> None:
    clock = iter([1000.0, 1000.0])
    scheduler = TaskScheduler(MemoryScheduleStore(), clock=lambda: next(clock))

    job = scheduler.schedule("t-1", delay_seconds=30)
    assert job.run_at == 1030.0
    assert job.task_id == "t-1"
    assert job.recurring is False


def test_schedule_explicit_run_at_wins_over_delay() -> None:
    scheduler = TaskScheduler(MemoryScheduleStore(), clock=lambda: 1000.0)
    job = scheduler.schedule("t-1", delay_seconds=30, run_at=5000.0)
    assert job.run_at == 5000.0


def test_due_jobs_returns_sorted_and_excludes_future() -> None:
    store = MemoryScheduleStore()
    scheduler = TaskScheduler(store, clock=lambda: 1000.0)
    late = scheduler.schedule("late", run_at=2000.0)
    scheduler.schedule("second", run_at=900.0)
    scheduler.schedule("first", run_at=800.0)

    due = scheduler.due_jobs()
    assert [job.task_id for job in due] == ["first", "second"]
    assert late.run_at > 1000.0


def test_complete_removes_one_shot_job() -> None:
    scheduler = TaskScheduler(MemoryScheduleStore(), clock=lambda: 1000.0)
    job = scheduler.schedule("t-1")

    scheduler.complete(job.job_id)
    assert scheduler.due_jobs() == []


def test_complete_unknown_job_raises() -> None:
    scheduler = TaskScheduler(MemoryScheduleStore(), clock=lambda: 1000.0)
    with pytest.raises(ScheduleError, match="unknown job"):
        scheduler.complete("nope")


def test_cancel_reports_whether_job_existed() -> None:
    scheduler = TaskScheduler(MemoryScheduleStore(), clock=lambda: 1000.0)
    job = scheduler.schedule("t-1")
    assert scheduler.cancel(job.job_id) is True
    assert scheduler.cancel(job.job_id) is False


# --- recurring --------------------------------------------------------------


def test_recurring_job_advances_by_interval_on_complete() -> None:
    now = [1000.0]
    scheduler = TaskScheduler(MemoryScheduleStore(), clock=lambda: now[0])

    job = scheduler.schedule_recurring("t-1", interval_seconds=60.0)
    assert job.run_at == 1000.0  # first run is due immediately

    scheduler.complete(job.job_id)
    assert scheduler.due_jobs() == []  # next run is one interval away

    now[0] = 1060.0
    (next_job,) = scheduler.due_jobs()
    assert next_job.job_id == job.job_id  # same job id, not a new one
    assert next_job.run_at == 1060.0
    assert next_job.attempts == 0


def test_recurring_rejects_non_positive_interval() -> None:
    scheduler = TaskScheduler(MemoryScheduleStore(), clock=lambda: 1000.0)
    with pytest.raises(ScheduleError, match="interval_seconds must be positive"):
        scheduler.schedule_recurring("t-1", interval_seconds=0)


def test_recurring_first_delay_applies() -> None:
    scheduler = TaskScheduler(MemoryScheduleStore(), clock=lambda: 1000.0)
    job = scheduler.schedule_recurring("t-1", 60.0, first_delay_seconds=15.0)
    assert job.run_at == 1015.0


# --- retries ----------------------------------------------------------------


def test_retry_backs_off_and_counts_attempts() -> None:
    now = [1000.0]
    scheduler = TaskScheduler(MemoryScheduleStore(), clock=lambda: now[0])
    job = scheduler.schedule("t-1", max_attempts=3)

    first = scheduler.retry(job.job_id)
    assert first.attempts == 1
    assert first.run_at == 1002.0  # 2s backoff

    now[0] = 1002.0
    second = scheduler.retry(job.job_id)
    assert second.attempts == 2
    assert second.run_at == 1006.0  # 4s backoff


def test_retry_exhaustion_deletes_job_and_raises() -> None:
    scheduler = TaskScheduler(MemoryScheduleStore(), clock=lambda: 1000.0)
    job = scheduler.schedule("t-1", max_attempts=2)

    scheduler.retry(job.job_id)  # attempt 1 -> rescheduled
    with pytest.raises(RetriesExhaustedError, match="exhausted 2 attempts"):
        scheduler.retry(job.job_id)  # attempt 2 -> dropped

    assert scheduler.due_jobs() == []


def test_retry_unknown_job_raises() -> None:
    scheduler = TaskScheduler(MemoryScheduleStore(), clock=lambda: 1000.0)
    with pytest.raises(ScheduleError, match="unknown job"):
        scheduler.retry("nope")


# --- redis store (with a test double) ---------------------------------------


class FakeRedis:
    """Minimal hash-command double for RedisScheduleStore."""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}

    def hset(self, key: str, field: str, value: str) -> int:
        created = field not in self.hashes.get(key, {})
        self.hashes.setdefault(key, {})[field] = value
        return int(created)

    def hget(self, key: str, field: str) -> str | None:
        return self.hashes.get(key, {}).get(field)

    def hdel(self, key: str, field: str) -> int:
        return int(self.hashes.get(key, {}).pop(field, None) is not None)

    def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))


def test_redis_store_roundtrip_and_delete() -> None:
    store = RedisScheduleStore(FakeRedis(), key="test:schedule")
    job = Job(job_id="j1", task_id="t-1", run_at=100.0)

    store.put(job)
    assert store.get("j1") == job
    assert store.all() == [job]

    assert store.delete("j1") is True
    assert store.delete("j1") is False
    assert store.get("j1") is None


def test_redis_store_handles_bytes_responses() -> None:
    class BytesRedis(FakeRedis):
        def hget(self, key: str, field: str) -> bytes | None:  # type: ignore[override]
            raw = super().hget(key, field)
            return raw.encode() if raw is not None else None

        def hgetall(self, key: str) -> dict[bytes, bytes]:  # type: ignore[override]
            return {k.encode(): v.encode() for k, v in super().hgetall(key).items()}

    store = RedisScheduleStore(BytesRedis())
    store.put(Job(job_id="j1", task_id="t-1", run_at=100.0))

    assert store.get("j1") == Job(job_id="j1", task_id="t-1", run_at=100.0)
    assert store.all() == [Job(job_id="j1", task_id="t-1", run_at=100.0)]


def test_scheduler_works_on_redis_store_end_to_end() -> None:
    now = [1000.0]
    scheduler = TaskScheduler(RedisScheduleStore(FakeRedis()), clock=lambda: now[0])

    job = scheduler.schedule("t-1", delay_seconds=10)
    assert scheduler.due_jobs() == []

    now[0] = 1010.0
    (due,) = scheduler.due_jobs()
    assert due.job_id == job.job_id

    scheduler.complete(job.job_id)
    assert scheduler.due_jobs() == []
