"""Engine and session factory creation for the configured database URL."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_engine_for(url: str) -> Engine:
    """Create an engine; SQLite gets check_same_thread=False for FastAPI."""
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **kwargs)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory bound to the engine."""
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
