"""Desktop boot: environment preparation and server start for the EXE.

Used two ways:

- **Frozen build** (PyInstaller): ``apps/desktop/entry.py`` imports this
  module; ``prepare()`` derives every setting from the user's app-data
  directory so double-clicking the EXE needs zero configuration.
- **Source run**: ``python -m services.desktop.boot`` behaves the same
  but keeps files in the repository (developer smoke-testing).

Precedence: an explicit ``WORKFORCE_*`` environment variable always wins,
so power users can still override the database, port or key.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import webbrowser
from collections.abc import MutableMapping
from pathlib import Path

DEFAULT_PORT = 8756  # away from the dev API's 8000


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """Resource root: PyInstaller's extraction dir, else the repo root."""
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2]


def app_data_dir() -> Path:
    """Per-user writable directory (Windows %LOCALAPPDATA%, else ~/.)."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "ShahidWorkforce"
    return Path.home() / ".shahid-workforce"


def ensure_api_key(config_path: Path) -> str:
    """Load the persisted API key, generating one on first launch."""
    if config_path.is_file():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            key = data.get("api_key")
            if isinstance(key, str) and key:
                return key
        except (json.JSONDecodeError, OSError):
            pass  # corrupt file: regenerate below
    key = f"wh-{secrets.token_urlsafe(32)}"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps({"api_key": key}, indent=2), encoding="utf-8"
    )
    return key


def resolve_dashboard_dir() -> Path | None:
    """Static export to serve: env override, bundled copy, or repo build."""
    env_dir = os.environ.get("WORKFORCE_DASHBOARD_DIR", "").strip()
    if env_dir:
        explicit = Path(env_dir)
        # An explicit-but-missing directory means "API only" rather than
        # a server that 404s every page.
        return explicit if explicit.is_dir() else None
    candidates = (
        bundle_root() / "dashboard",  # frozen: shipped inside the bundle
        bundle_root() / "apps" / "dashboard" / "out",  # source checkout
    )
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return None


def prepare(env: MutableMapping[str, str] | None = None) -> Path:
    """Fill WORKFORCE_* env vars (without overriding explicit ones).

    ``env`` defaults to the process environment; tests inject a dict.
    Returns the app-data directory actually used.
    """
    target: MutableMapping[str, str] = env if env is not None else os.environ
    data_dir = app_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    if not target.get("WORKFORCE_API_KEY"):
        target["WORKFORCE_API_KEY"] = ensure_api_key(data_dir / "config.json")
    target.setdefault(
        "WORKFORCE_DATABASE_URL",
        f"sqlite:///{data_dir / 'workforce.db'}",
    )
    target.setdefault("WORKFORCE_ENV", "development")
    target.setdefault("WORKFORCE_AUTO_RUN", "1")
    target.setdefault("WORKFORCE_PORT", str(DEFAULT_PORT))

    dashboard = resolve_dashboard_dir()
    if dashboard is not None:
        target.setdefault("WORKFORCE_DASHBOARD_DIR", str(dashboard))
    return data_dir


def open_browser_later(url: str, delay_seconds: float = 2.0) -> None:
    """Open the dashboard once the server has had a moment to bind."""
    timer = threading.Timer(delay_seconds, lambda: webbrowser.open(url))
    timer.daemon = True
    timer.start()


def main() -> None:
    """Start the packaged server: dashboard + API in one process."""
    import uvicorn

    prepare()
    port = int(os.environ.get("WORKFORCE_PORT", str(DEFAULT_PORT)))
    url = f"http://127.0.0.1:{port}/"

    # Import after prepare() so create_app() reads the derived settings.
    from services.api.main import create_app

    open_browser_later(url)
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
