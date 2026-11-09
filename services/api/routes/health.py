"""Public health endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from services.api.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    """Liveness probe; requires no authentication."""
    return HealthOut(status="ok")
