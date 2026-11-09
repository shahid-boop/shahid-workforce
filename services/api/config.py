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

    @property
    def is_production(self) -> bool:
        return self.env == "production"


def settings_from_env() -> Settings:
    """Build settings from WORKFORCE_* environment variables."""
    origins_raw = os.environ.get("WORKFORCE_CORS_ORIGINS", "")
    origins = tuple(
        origin.strip() for origin in origins_raw.split(",") if origin.strip()
    ) or DEFAULT_CORS_ORIGINS
    return Settings(
        env=os.environ.get("WORKFORCE_ENV", "development"),
        api_key=os.environ.get("WORKFORCE_API_KEY") or None,
        database_url=os.environ.get(
            "WORKFORCE_DATABASE_URL", "sqlite:///./workforce.db"
        ),
        cors_origins=origins,
    )
