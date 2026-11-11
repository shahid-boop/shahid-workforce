"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { TaskDetail } from "@/features/tasks/task-detail";

/**
 * Query-param wrapper around ``TaskDetail`` so the task view is a static
 * route (`/tasks?id=...`) that survives a full static export - dynamic
 * segments like `/tasks/[id]` cannot be prerendered.
 */
function TaskView() {
  const params = useSearchParams();
  const taskId = params.get("id");

  // useSearchParams needs a Suspense boundary for static rendering; the
  // fallback is only visible before the router resolves the query string.
  if (!taskId) {
    return (
      <div className="panel">
        <p className="error">No task selected.</p>
        <a href="/">← Back to tasks</a>
      </div>
    );
  }
  return <TaskDetail taskId={taskId} />;
}

export function TaskViewSuspense() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return <p className="muted">Loading task…</p>;
  return (
    <Suspense fallback={<p className="muted">Loading task…</p>}>
      <TaskView />
    </Suspense>
  );
}
