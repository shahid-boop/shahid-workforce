import Link from "next/link";

import type { Task } from "@/lib/api";

interface TaskListProps {
  tasks: Task[];
  onDelete: (taskId: string) => Promise<void>;
}

/** Simple task table with status badges, detail links and a delete action. */
export function TaskList({ tasks, onDelete }: TaskListProps) {
  return (
    <ul className="task-list">
      {tasks.map((task) => (
        <li key={task.id} className="task-row">
          <div>
            <div className="task-title">
              <Link href={`/tasks?id=${encodeURIComponent(task.id)}`}>
                {task.title}
              </Link>
            </div>
            {task.description ? (
              <div className="task-desc">{task.description}</div>
            ) : null}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className={`status status-${task.status}`}>{task.status}</span>
            <button
              type="button"
              aria-label={`Delete ${task.title}`}
              onClick={() => void onDelete(task.id)}
            >
              Delete
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
