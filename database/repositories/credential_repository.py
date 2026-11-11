"""Persistence for provider keys entered through the settings UI.

Writes go through the API's own session. Reads used by the model router
create a short-lived engine from the runtime database URL (process
override first, then ``WORKFORCE_DATABASE_URL``); a missing URL or an
unreadable database simply yields ``None`` - credential discovery stays
fail-open, exactly like a missing environment variable.
"""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from database.connection import create_engine_for
from database.models import ProviderCredential

# Set by the API app factory so in-process credential reads hit the same
# database the app writes to, even when WORKFORCE_DATABASE_URL is unset.
_runtime_url: str | None = None


def set_runtime_database_url(url: str | None) -> None:
    """Point credential reads at ``url`` (None restores env-only discovery)."""
    global _runtime_url
    _runtime_url = url


def runtime_database_url() -> str | None:
    """Effective URL for credential reads: process override, then env."""
    return _runtime_url or os.environ.get("WORKFORCE_DATABASE_URL") or None


def get_credential(session: Session, provider: str) -> ProviderCredential | None:
    """Fetch one stored credential row by provider id."""
    return session.get(ProviderCredential, provider)


def upsert_credential(
    session: Session,
    provider: str,
    *,
    api_key: str,
    base_url: str | None = None,
) -> ProviderCredential:
    """Insert or update the stored credential for ``provider``.

    A ``None`` ``base_url`` keeps the existing endpoint so a key-only
    update never wipes a configured URL (and vice versa).
    """
    row = session.get(ProviderCredential, provider)
    if row is None:
        row = ProviderCredential(provider=provider, api_key=api_key, base_url=base_url)
        session.add(row)
    else:
        row.api_key = api_key
        if base_url is not None:
            row.base_url = base_url
    session.commit()
    return row


def delete_credential(session: Session, provider: str) -> bool:
    """Remove the stored credential; ``False`` when nothing was stored."""
    row = session.get(ProviderCredential, provider)
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True


def read_stored_credential(provider: str) -> ProviderCredential | None:
    """Read one row with a throwaway engine; fail-open on any problem.

    Used by :func:`services.model_router.providers.credential_for`, which
    must never raise just because the database is absent or locked.
    """
    url = runtime_database_url()
    if not url:
        return None
    engine = create_engine_for(url)
    try:
        with Session(engine) as session:
            return session.get(ProviderCredential, provider)
    except Exception:
        # Table missing, database locked, bad URL: treat as "no key".
        return None
    finally:
        engine.dispose()
