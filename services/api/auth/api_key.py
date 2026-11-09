"""X-API-Key dependency.

Rules:
- Production fails closed: create_app refuses to start without an API key.
- When a key is configured it must match (constant-time comparison).
- Development without a key stays open for local work.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Request, status

from services.api.config import Settings


def get_settings(request: Request) -> Settings:
    """Return the settings bound to the app instance."""
    return request.app.state.settings


async def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Reject requests without a valid X-API-Key on private routes."""
    settings = get_settings(request)
    if settings.api_key is None:
        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="API key authentication is not configured",
            )
        return  # development mode without a key: open
    provided = (x_api_key or "").encode()
    expected = settings.api_key.encode()
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
