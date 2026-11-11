"""Provider credentials: manually stored API keys.

Revision ID: 0002_provider_credentials
Revises: 0001_initial_tasks
Create Date: 2026-11-11

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_provider_credentials"
down_revision: str | None = "0001_initial_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_credentials",
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("provider"),
    )


def downgrade() -> None:
    op.drop_table("provider_credentials")
