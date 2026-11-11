"""Static dashboard serving for the packaged Windows build.

The dashboard can be exported as pure static HTML
(``apps/dashboard: npm run build:static``) and served by this same API
process, giving a single-process app with no Node.js requirement. Two
special behaviours:

- **Key injection:** every served HTML page gets
  ``window.__WF_KEY="<api key>"`` injected into ``<head>``. The exported
  pages call ``/api/*`` directly (they have no Next.js proxy layer), and
  ``apiFetch`` attaches the key as ``X-API-Key`` - auth stays fail-closed.
- **SPA fallback:** unknown non-API paths serve the app shell (or the
  export's ``404.html``), because Next.js static routes live in
  per-route ``index.html`` files.

Only ``Settings.dashboard_dir`` enables this; dev/CI APIs stay API-only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

if TYPE_CHECKING:
    from fastapi import FastAPI


def inject_key(html: str, api_key: str | None) -> str:
    """Embed the runtime API key so the static pages can authenticate."""
    if not api_key:
        return html
    tag = f"<script>window.__WF_KEY={json.dumps(api_key)};</script>"
    if "</head>" in html:
        return html.replace("</head>", tag + "</head>", 1)
    return tag + html


def install_dashboard(app: FastAPI, directory: str, api_key: str | None) -> None:
    """Serve the static export from ``directory`` on every unmatched path."""
    root = Path(directory).resolve()

    def html_response(path: Path, status_code: int = 200) -> HTMLResponse:
        rendered = inject_key(path.read_text(encoding="utf-8"), api_key)
        return HTMLResponse(rendered, status_code=status_code)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def dashboard_files(full_path: str) -> object:
        # The API surface keeps its own JSON 404s - never HTML.
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse({"error": "not found"}, status_code=404)

        target = (root / full_path).resolve()
        if not target.is_relative_to(root):
            return JSONResponse({"error": "not found"}, status_code=404)

        if target.is_file():
            if target.suffix == ".html":
                return html_response(target)
            return FileResponse(target)

        # Next export with trailingSlash: `/tasks` -> `tasks/index.html`.
        index = target / "index.html"
        if index.is_file():
            return html_response(index)

        # Unknown path: prefer the export's styled 404 page.
        not_found = root / "404.html"
        if not_found.is_file():
            return html_response(not_found, status_code=404)
        shell = root / "index.html"
        if shell.is_file():
            return html_response(shell)
        return JSONResponse({"error": "dashboard not built"}, status_code=404)

    # Registered after the API routers, so /tasks, /agents,
    # /settings/providers, /docs etc. always win over the catch-all.
