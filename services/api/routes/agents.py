"""Agent registry endpoints (private: X-API-Key required)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from agents.registry import load_agents
from services.api.auth.api_key import require_api_key
from services.api.schemas import AgentList, AgentOut

router = APIRouter(
    prefix="/agents",
    tags=["agents"],
    dependencies=[Depends(require_api_key)],
)


@router.get("", response_model=AgentList)
def list_agents() -> AgentList:
    """List every configured specialist agent (prompt text is never exposed)."""
    agents = [
        AgentOut(
            id=definition.id,
            name=definition.name,
            department=definition.department,
            model=definition.model,
        )
        for definition in load_agents()
    ]
    return AgentList(items=agents, count=len(agents))
