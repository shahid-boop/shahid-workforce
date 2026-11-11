"""Provider credential model: API keys entered through the settings UI.

Stored rows are a manual alternative to environment variables; env vars
always win during resolution. The key column never leaves the server in
full - responses only ever carry a masked prefix.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ProviderCredential(Base):
    """One manually stored provider key (and optional custom endpoint)."""

    __tablename__ = "provider_credentials"

    provider: Mapped[str] = mapped_column(String(30), primary_key=True)
    api_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
