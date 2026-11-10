import { TaskDetail } from "@/features/tasks/task-detail";

export const metadata = { title: "Task · Shahid Workforce" };

export default async function TaskPage({
  params,
}: {
  params: Promise<{ taskId: string }>;
}) {
  const { taskId } = await params;
  return (
    <section>
      <h1>Task</h1>
      <TaskDetail taskId={taskId} />
    </section>
  );
}
