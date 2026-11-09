"""FastAPI application factory.

The module-level ``app`` attribute is created lazily (PEP 562) so importing
this module in tests has no environment or filesystem side effects; uvicorn
still resolves ``services.api.main:app`` normally.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database.connection import create_engine_for, create_session_factory
from database.models import Base
from services.api.config import Settings, settings_from_env
from services.api.middleware.security import SecurityHeadersMiddleware
from services.api.routes import health, tasks


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API application with the given (or env-derived) settings."""
    settings = settings or settings_from_env()
    if settings.is_production and not settings.api_key:
        raise RuntimeError(
            "WORKFORCE_API_KEY must be set when WORKFORCE_ENV=production"
        )

    app = FastAPI(
        title="Shahid AI Workforce API",
        version="0.1.0",
        description="Task and agent API for the Shahid AI workforce.",
    )
    app.state.settings = settings

    engine = create_engine_for(settings.database_url)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

    # Development convenience: create the SQLite schema automatically.
    # Production schema is managed with alembic and never mutated at startup.
    if not settings.is_production:
        Base.metadata.create_all(engine)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(tasks.router)
    return app


_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    """Lazily expose the ASGI ``app`` object (see module docstring)."""
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["create_app"]
