/**
 * Browser-side fetch for the dashboard's `/api/*` calls.
 *
 * Two modes, both same-origin:
 *
 * - **Dev (Next.js):** `/api/*` are Next route handlers that call the
 *   workforce API server-side with `WORKFORCE_API_KEY`; the browser sends
 *   no credentials at all.
 * - **Static/EXE (packaged):** the dashboard is a plain export served by
 *   the FastAPI app itself, which injects `window.__WF_KEY` into the HTML
 *   at serve time. The key then rides along here as `X-API-Key`, so the
 *   API stays fail-closed even in the single-file build.
 */

export function apiFetch(
  input: string,
  init?: RequestInit,
): Promise<Response> {
  const key =
    typeof window !== "undefined"
      ? (window as { __WF_KEY?: string }).__WF_KEY
      : undefined;
  if (!key) {
    return fetch(input, init);
  }
  const headers = new Headers(init?.headers);
  headers.set("X-API-Key", key);
  return fetch(input, { ...init, headers });
}
