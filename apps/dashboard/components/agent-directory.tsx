"use client";

import { useEffect, useState } from "react";

import type { Agent } from "@/lib/api";
import { apiFetch } from "@/lib/client-api";

interface AgentDirectoryState {
  agents: Agent[];
  loading: boolean;
  error: string | null;
}

/** Read-only directory of specialist agents loaded from `/api/agents`. */
export function AgentDirectory() {
  const [state, setState] = useState<AgentDirectoryState>({
    agents: [],
    loading: true,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await apiFetch("/api/agents", { cache: "no-store" });
        if (!response.ok) {
          const body = (await response.json()) as { error?: string };
          throw new Error(body.error ?? `request failed (${response.status})`);
        }
        const data = (await response.json()) as { items: Agent[] };
        if (!cancelled) {
          setState({ agents: data.items, loading: false, error: null });
        }
      } catch (error) {
        if (!cancelled) {
          setState((prev) => ({
            ...prev,
            loading: false,
            error: error instanceof Error ? error.message : "unknown error",
          }));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.loading) return <p className="muted">Loading agents…</p>;
  if (state.error) return <p className="error">{state.error}</p>;
  if (state.agents.length === 0) {
    return <p className="muted">No agents configured.</p>;
  }

  return (
    <ul className="task-list">
      {state.agents.map((agent) => (
        <li key={agent.id} className="task-row">
          <div>
            <div className="task-title">{agent.name}</div>
            <div className="task-desc">{agent.id}</div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="status">{agent.department}</span>
            {agent.model ? (
              <span className="muted" style={{ fontSize: 13 }}>
                {agent.model}
              </span>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  );
}
