"""FastAPI application factory.

The module-level ``app`` attribute is created lazily (PEP 562) so importing
this module in tests has no environment or filesystem side effects; uvicorn
still resolves ``services.api.main:app`` normally.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from database.connection import create_engine_for, create_session_factory
from database.models import Base
from database.repositories import credential_repository
from services.api.config import Settings, settings_from_env
from services.api.dashboard import install_dashboard
from services.api.middleware.security import SecurityHeadersMiddleware
from services.api.routes import agents, health, tasks
from services.api.routes import settings as settings_routes


def register_api_error_handlers(app: FastAPI) -> None:
    """`/api/*` mirrors answer with the dashboard's `{error}` JSON shape.

    The Next.js proxies translate FastAPI's `{"detail": ...}` into
    `{"error": ...}` for the browser. In the packaged build the dashboard
    calls these same endpoints directly through the `/api` prefix, so the
    translation happens here instead - at the cost of one path check.
    Every other route keeps FastAPI's default shapes.
    """

    def is_api_path(request: Request) -> bool:
        return request.url.path.startswith("/api/")

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if is_api_path(request):
            detail = exc.detail
            message = detail if isinstance(detail, str) else "request failed"
            return JSONResponse(
                {"error": message},
                status_code=exc.status_code,
                headers=exc.headers,
            )
        return await http_exception_handler(request, exc)  # type: ignore[return-value]

    @app.exception_handler(RequestValidationError)
    async def validation_exc(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        if is_api_path(request):
            return JSONResponse({"error": "validation failed"}, status_code=422)
        return await request_validation_exception_handler(request, exc)  # type: ignore[return-value]


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

    # Model-router credential reads must hit this same database, even when
    # WORKFORCE_DATABASE_URL is not exported (dev default URL).
    credential_repository.set_runtime_database_url(settings.database_url)

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
    register_api_error_handlers(app)

    app.include_router(health.router)
    app.include_router(tasks.router)
    app.include_router(agents.router)
    app.include_router(settings_routes.router)

    # `/api/*` mirrors of the dashboard-facing routers: identical handlers
    # and JSON, but with the `{error}` shape the browser client expects.
    # In dev the Next.js proxies call the unprefixed routes instead.
    app.include_router(tasks.router, prefix="/api")
    app.include_router(agents.router, prefix="/api")
    app.include_router(settings_routes.router, prefix="/api")

    # Packaged build: serve the static dashboard export from this process.
    # Registered last so every API route keeps priority over the catch-all.
    if settings.dashboard_dir:
        install_dashboard(app, settings.dashboard_dir, settings.api_key)
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
