"""Runtime settings read from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_CORS_ORIGINS = ("http://localhost:5173",)


@dataclass(frozen=True)
class Settings:
    """Immutable runtime configuration."""

    env: str = "development"
    api_key: str | None = None
    database_url: str = "sqlite:///./workforce.db"
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    # Development executes tasks inline after creation; production leaves
    # them queued for the Redis/RQ worker.
    auto_run: bool = False
    # Packaged (EXE) mode: directory of the static dashboard export to
    # serve from this API process. None = API-only (dev/CI).
    dashboard_dir: str | None = None

    @property
    def is_production(self) -> bool:
        return self.env == "production"


def settings_from_env() -> Settings:
    """Build settings from WORKFORCE_* environment variables."""
    origins_raw = os.environ.get("WORKFORCE_CORS_ORIGINS", "")
    origins = tuple(
        origin.strip() for origin in origins_raw.split(",") if origin.strip()
    ) or DEFAULT_CORS_ORIGINS
    env = os.environ.get("WORKFORCE_ENV", "development")
    auto_run_raw = os.environ.get("WORKFORCE_AUTO_RUN", "").strip().lower()
    if auto_run_raw:
        auto_run = auto_run_raw in ("1", "true", "yes", "on")
    else:
        auto_run = env != "production"
    return Settings(
        env=env,
        api_key=os.environ.get("WORKFORCE_API_KEY") or None,
        database_url=os.environ.get(
            "WORKFORCE_DATABASE_URL", "sqlite:///./workforce.db"
        ),
        cors_origins=origins,
        auto_run=auto_run,
        dashboard_dir=os.environ.get("WORKFORCE_DASHBOARD_DIR") or None,
    )
