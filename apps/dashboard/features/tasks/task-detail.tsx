"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import type { Task, TaskStatus } from "@/lib/api";
import { apiFetch } from "@/lib/client-api";

/** Ordered pipeline used for the progress indicator. */
const PIPELINE: TaskStatus[] = [
  "pending",
  "queued",
  "running",
  "completed",
];

const PROGRESS: Record<TaskStatus, number> = {
  pending: 0,
  queued: 25,
  running: 60,
  completed: 100,
  failed: 100,
  cancelled: 100,
};

interface TaskDetailState {
  task: Task | null;
  loading: boolean;
  error: string | null;
}

/**
 * Single-task view: loads through the `/api/tasks/[id]` proxy and polls
 * while the task is still moving (pending → queued → running).
 */
export function TaskDetail({ taskId }: { taskId: string }) {
  const [state, setState] = useState<TaskDetailState>({
    task: null,
    loading: true,
    error: null,
  });

  const load = useCallback(async () => {
    try {
      const response = await apiFetch(`/api/tasks/${taskId}`, {
        cache: "no-store",
      });
      if (response.status === 404) {
        setState({ task: null, loading: false, error: "task not found" });
        return;
      }
      if (!response.ok) {
        const body = (await response.json()) as { error?: string };
        throw new Error(body.error ?? `request failed (${response.status})`);
      }
      const task = (await response.json()) as Task;
      setState({ task, loading: false, error: null });
    } catch (error) {
      setState((prev) => ({
        ...prev,
        loading: false,
        error: error instanceof Error ? error.message : "unknown error",
      }));
    }
  }, [taskId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Poll every 3s while the task is active; stop once it settles.
  const active =
    state.task !== null &&
    ["pending", "queued", "running"].includes(state.task.status);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => void load(), 3000);
    return () => clearInterval(timer);
  }, [active, load]);

  if (state.loading) return <p className="muted">Loading task…</p>;
  if (state.error) {
    return (
      <div className="panel">
        <p className="error">{state.error}</p>
        <Link href="/">← Back to tasks</Link>
      </div>
    );
  }
  if (!state.task) return null;

  const task = state.task;
  const percent = PROGRESS[task.status];
  const isFailure = task.status === "failed" || task.status === "cancelled";

  return (
    <div className="panel">
      <p>
        <Link href="/">← Back to tasks</Link>
      </p>
      <h2>{task.title}</h2>
      <p className="muted">
        <code>{task.id}</code>
      </p>
      <p>
        <span className={`status status-${task.status}`}>{task.status}</span>
      </p>

      <div
        className="progress-track"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Task progress"
      >
        <div
          className={`progress-fill${isFailure ? " progress-fail" : ""}`}
          style={{ width: `${percent}%` }}
        />
      </div>

      <ol className="pipeline">
        {PIPELINE.map((step) => {
          const reached =
            PIPELINE.indexOf(step) <= PIPELINE.indexOf(task.status as TaskStatus) ||
            task.status === "completed";
          const current = task.status === step;
          return (
            <li
              key={step}
              className={`pipeline-step${reached ? " reached" : ""}${
                current ? " current" : ""
              }`}
            >
              {step}
            </li>
          );
        })}
      </ol>

      {task.description ? <p>{task.description}</p> : null}

      {task.result ? (
        <>
          <h3>Result</h3>
          <pre className="task-result">{task.result}</pre>
        </>
      ) : (
        <p className="muted">No result yet.</p>
      )}

      <p className="muted" style={{ fontSize: 13 }}>
        Created {new Date(task.created_at).toLocaleString()} · Updated{" "}
        {new Date(task.updated_at).toLocaleString()}
        {active ? " · auto-refreshing…" : ""}
      </p>
    </div>
  );
}
