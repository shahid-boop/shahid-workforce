/** Proxy for `GET /agents` on the workforce API. */

import { NextResponse } from "next/server";

import { listAgents, errorInfo } from "@/lib/api";

export async function GET() {
  try {
    const agents = await listAgents();
    return NextResponse.json(agents);
  } catch (error) {
    const info = errorInfo(error);
    return NextResponse.json({ error: info.message }, { status: info.status });
  }
}
