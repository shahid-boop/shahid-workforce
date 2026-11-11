/** Proxy for `PUT`/`DELETE /settings/providers/{provider}` on the workforce API. */

import { NextResponse } from "next/server";

import { deleteProviderKey, saveProviderKey, errorInfo } from "@/lib/api";

export async function PUT(
  request: Request,
  context: { params: Promise<{ provider: string }> },
) {
  const { provider } = await context.params;

  try {
    const payload = (await request.json()) as {
      api_key?: string;
      base_url?: string;
    };
    const status = await saveProviderKey(provider, payload);
    return NextResponse.json(status);
  } catch (error) {
    const info = errorInfo(error);
    return NextResponse.json({ error: info.message }, { status: info.status });
  }
}

export async function DELETE(
  _request: Request,
  context: { params: Promise<{ provider: string }> },
) {
  const { provider } = await context.params;

  try {
    const status = await deleteProviderKey(provider);
    return NextResponse.json(status);
  } catch (error) {
    const info = errorInfo(error);
    return NextResponse.json({ error: info.message }, { status: info.status });
  }
}
