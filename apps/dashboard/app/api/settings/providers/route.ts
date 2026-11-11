/** Proxy for `GET /settings/providers` on the workforce API. */

import { NextResponse } from "next/server";

import { listProviderStatuses, errorInfo } from "@/lib/api";

export async function GET() {
  try {
    const providers = await listProviderStatuses();
    return NextResponse.json(providers);
  } catch (error) {
    const info = errorInfo(error);
    return NextResponse.json({ error: info.message }, { status: info.status });
  }
}
