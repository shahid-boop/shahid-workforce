/**
 * Proxy for `GET/POST /tasks` on the workforce API.
 *
 * The upstream API key stays server-side; the browser only ever talks to this
 * route. Errors are normalised to `{ error }` JSON for the client board.
 */

import { NextResponse } from "next/server";

import { createTask, listTasks, errorInfo } from "@/lib/api";

export async function GET(request: Request) {
  const limitParam = new URL(request.url).searchParams.get("limit");
  const limit = limitParam ? Number(limitParam) : 50;

  try {
    const tasks = await listTasks(Number.isFinite(limit) ? limit : 50);
    return NextResponse.json(tasks);
  } catch (error) {
    const info = errorInfo(error);
    return NextResponse.json({ error: info.message }, { status: info.status });
  }
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const title =
    typeof body === "object" && body !== null && "title" in body
      ? (body as { title?: unknown }).title
      : undefined;

  if (typeof title !== "string" || title.trim().length === 0) {
    return NextResponse.json({ error: "title is required" }, { status: 400 });
  }
  if (title.length > 200) {
    return NextResponse.json(
      { error: "title must be 200 characters or fewer" },
      { status: 400 },
    );
  }

  try {
    const task = await createTask({ title: title.trim() });
    return NextResponse.json(task, { status: 201 });
  } catch (error) {
    const info = errorInfo(error);
    return NextResponse.json({ error: info.message }, { status: info.status });
  }
}
