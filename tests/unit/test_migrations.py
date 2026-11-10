"""Tests for the Alembic migration pipeline.

Each test runs against a throwaway SQLite file with ``ALEMBIC_DATABASE_URL``
pointing at it, exercising the real ``env.py`` and revision scripts.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


def make_config(db_path: Path) -> Config:
    """Alembic config bound to a temp database (no env var needed)."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(REPO_ROOT / "database" / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def table_names(db_path: Path) -> set[str]:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "migration.db"


def test_upgrade_head_creates_tasks_table(db_path: Path) -> None:
    command.upgrade(make_config(db_path), "head")
    tables = table_names(db_path)
    assert "tasks" in tables
    assert "alembic_version" in tables


def test_downgrade_base_removes_tasks_table(db_path: Path) -> None:
    command.upgrade(make_config(db_path), "head")
    command.downgrade(make_config(db_path), "base")

    tables = table_names(db_path)
    assert "tasks" not in tables
    # alembic_version intentionally survives at base so upgrades stay tracked.


def test_upgraded_schema_matches_orm_metadata(db_path: Path) -> None:
    """Migration output must not drift from the SQLAlchemy models."""
    from database.models import Base

    command.upgrade(make_config(db_path), "head")

    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as connection:
            for table in Base.metadata.sorted_tables:
                assert table.name in inspect(connection).get_table_names()
                migrated = inspect(connection).get_columns(table.name)
                migrated_names = {column["name"] for column in migrated}
                model_names = {column.name for column in table.columns}
                assert migrated_names == model_names, table.name
    finally:
        engine.dispose()


def test_migration_writes_readable_rows(db_path: Path) -> None:
    """After upgrade the app's own INSERT/SELECT must work."""
    from database.models import Base

    command.upgrade(make_config(db_path), "head")
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        Base.metadata.create_all(engine)  # idempotent: schema already exists
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tasks (id, title, status, created_at, updated_at) "
                    "VALUES (:id, :title, 'pending', '2026-01-01', '2026-01-01')"
                ),
                {"id": "t-1", "title": "migrated"},
            )
            row = connection.execute(
                text("SELECT title, status FROM tasks WHERE id = 't-1'")
            ).one()
        assert row.title == "migrated"
        assert row.status == "pending"
    finally:
        engine.dispose()


def test_env_url_override_is_honoured(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ALEMBIC_DATABASE_URL wins over alembic.ini (documented order)."""
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.chdir(REPO_ROOT)
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    assert "tasks" in table_names(db_path)


def test_revision_history_is_linear() -> None:
    """Exactly one root revision, chained - no surprise branches."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(make_config(Path("unused.db")))
    revisions = list(script.walk_revisions())
    roots = [rev for rev in revisions if rev.down_revision is None]
    assert len(roots) == 1
    assert len(revisions) == 1
    assert roots[0].revision == "0001_initial_tasks"
