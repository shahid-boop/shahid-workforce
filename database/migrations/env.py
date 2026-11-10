"""Alembic environment: wires migrations to the app's models and metadata.

URL resolution order:

1. ``ALEMBIC_DATABASE_URL`` (explicit override, used by tests)
2. ``WORKFORCE_DATABASE_URL`` (same variable the API uses)
3. ``sqlalchemy.url`` from ``alembic.ini`` (local sqlite default)
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from database.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

override_url = os.environ.get("ALEMBIC_DATABASE_URL") or os.environ.get(
    "WORKFORCE_DATABASE_URL"
)
if override_url:
    config.set_main_option("sqlalchemy.url", override_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live database connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite") if url else False,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    connectable = config.attributes.get("connection", None)

    if connectable is None:
        section = config.get_section(config.config_ini_section, {})
        engine = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
        with engine.connect() as connection:
            _run_with_connection(connection)
        engine.dispose()
    else:
        _run_with_connection(connectable)


def _run_with_connection(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
    )

    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
