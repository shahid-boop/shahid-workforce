"use client";

import { useCallback, useEffect, useState } from "react";

import { TaskForm } from "@/components/task-form";
import { TaskList } from "@/components/task-list";
import type { Task } from "@/lib/api";
import { apiFetch } from "@/lib/client-api";

interface TaskBoardState {
  tasks: Task[];
  loading: boolean;
  error: string | null;
}

/**
 * Client-side board: loads tasks from the local proxy route and exposes
 * create/delete actions. The real API key never leaves the server.
 */
export function TaskBoard() {
  const [state, setState] = useState<TaskBoardState>({
    tasks: [],
    loading: true,
    error: null,
  });

  const load = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const response = await apiFetch("/api/tasks?limit=50", { cache: "no-store" });
      if (!response.ok) {
        const body = (await response.json()) as { error?: string };
        throw new Error(body.error ?? `request failed (${response.status})`);
      }
      const data = (await response.json()) as { items: Task[] };
      setState({ tasks: data.items, loading: false, error: null });
    } catch (error) {
      setState((prev) => ({
        ...prev,
        loading: false,
        error: error instanceof Error ? error.message : "unknown error",
      }));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const create = async (title: string) => {
    const response = await apiFetch("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (!response.ok) {
      const body = (await response.json()) as { error?: string };
      throw new Error(body.error ?? `create failed (${response.status})`);
    }
    await load();
  };

  const remove = async (taskId: string) => {
    const response = await apiFetch(`/api/tasks/${taskId}`, { method: "DELETE" });
    if (!response.ok && response.status !== 404) {
      const body = (await response.json()) as { error?: string };
      throw new Error(body.error ?? `delete failed (${response.status})`);
    }
    await load();
  };

  return (
    <>
      <div className="panel">
        <TaskForm onSubmit={create} />
        {state.error ? <p className="error">{state.error}</p> : null}
      </div>
      <div className="panel">
        {state.loading ? (
          <p className="muted">Loading tasks…</p>
        ) : state.tasks.length === 0 ? (
          <p className="muted">No tasks yet. Create the first one above.</p>
        ) : (
          <TaskList tasks={state.tasks} onDelete={remove} />
        )}
      </div>
    </>
  );
}
