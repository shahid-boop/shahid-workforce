"use client";

import { useCallback, useEffect, useState } from "react";

import type { Task } from "@/lib/api";
import { apiFetch } from "@/lib/client-api";

interface UseTasksResult {
  tasks: Task[];
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
}

/**
 * Load tasks from the dashboard's own `/api/tasks` proxy route.
 * Polling is intentionally left out; callers trigger `reload` explicitly.
 */
export function useTasks(limit = 50): UseTasksResult {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiFetch(`/api/tasks?limit=${limit}`, {
        cache: "no-store",
      });
      if (!response.ok) {
        const body = (await response.json()) as { error?: string };
        throw new Error(body.error ?? `request failed (${response.status})`);
      }
      const data = (await response.json()) as { items: Task[] };
      setTasks(data.items);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "unknown error");
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { tasks, loading, error, reload };
}
