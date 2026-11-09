/** Proxy for `DELETE /tasks/{id}` on the workforce API. */

import { NextResponse } from "next/server";

import { deleteTask, errorInfo, ApiError } from "@/lib/api";

export async function DELETE(
  _request: Request,
  context: { params: Promise<{ taskId: string }> },
) {
  const { taskId } = await context.params;

  try {
    await deleteTask(taskId);
    return new NextResponse(null, { status: 204 });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return NextResponse.json({ error: "task not found" }, { status: 404 });
    }
    const info = errorInfo(error);
    return NextResponse.json({ error: info.message }, { status: info.status });
  }
}
