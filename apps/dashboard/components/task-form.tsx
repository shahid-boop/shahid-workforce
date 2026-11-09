"use client";

import { useState } from "react";

interface TaskFormProps {
  onSubmit: (title: string) => Promise<void>;
}

/** Controlled form that creates a task and resets on success. */
export function TaskForm({ onSubmit }: TaskFormProps) {
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed || busy) return;

    setBusy(true);
    setError(null);
    try {
      await onSubmit(trimmed);
      setTitle("");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="task-form" onSubmit={handleSubmit}>
      <input
        aria-label="Task title"
        placeholder="What should the workforce do?"
        value={title}
        maxLength={200}
        onChange={(event) => setTitle(event.target.value)}
      />
      <button type="submit" disabled={busy || title.trim().length === 0}>
        {busy ? "Creating…" : "Create task"}
      </button>
      {error ? <p className="error">{error}</p> : null}
    </form>
  );
}
