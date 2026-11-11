"""Pydantic request/response models for the API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TaskStatus = Literal[
    "pending", "queued", "running", "completed", "failed", "cancelled"
]


class TaskCreate(BaseModel):
    """Payload for creating a task."""

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)


class TaskUpdate(BaseModel):
    """Payload for updating a task."""

    status: TaskStatus | None = None
    result: str | None = Field(default=None, max_length=100_000)


class TaskOut(BaseModel):
    """Serialized task."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str | None
    status: str
    result: str | None
    created_at: datetime
    updated_at: datetime


class TaskList(BaseModel):
    """A page of tasks."""

    items: list[TaskOut]
    count: int


class HealthOut(BaseModel):
    """Health probe response."""

    status: str


class AgentOut(BaseModel):
    """Serialized specialist agent (prompt text stays server-side)."""

    id: str
    name: str
    department: str
    model: str | None = None


class AgentList(BaseModel):
    """All configured agents."""

    items: list[AgentOut]
    count: int


class ProviderKeyUpdate(BaseModel):
    """Payload for storing a provider key (and optional endpoint) manually."""

    api_key: str | None = Field(default=None, min_length=1, max_length=4096)
    base_url: str | None = Field(default=None, max_length=500)


class ProviderStatus(BaseModel):
    """Provider credential status; the full key is never returned."""

    provider: str
    configured: bool
    source: str | None = None  # "env" | "stored"
    key_masked: str | None = None
    base_url: str | None = None
    stored: bool = False


class ProviderStatusList(BaseModel):
    """Every provider known to the model router."""

    items: list[ProviderStatus]
    count: int
