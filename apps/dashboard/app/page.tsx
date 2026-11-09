import { TaskBoard } from "@/features/tasks/task-board";

export default function HomePage() {
  return (
    <section>
      <h1>Tasks</h1>
      <p className="muted">
        Create and monitor workforce tasks. The board loads from the API and
        refreshes manually.
      </p>
      <TaskBoard />
    </section>
  );
}
