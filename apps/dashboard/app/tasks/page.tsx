import { TaskViewSuspense } from "@/features/tasks/task-view";

export const metadata = { title: "Task · Shahid Workforce" };

export default function TaskPage() {
  return (
    <section>
      <h1>Task</h1>
      <TaskViewSuspense />
    </section>
  );
}
