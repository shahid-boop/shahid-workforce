"""Provider key management endpoints (private: X-API-Key required).

Keys entered here are stored in the database and never returned in full:
responses carry only a short masked prefix. Environment variables always
override stored keys, so deployments can keep using ``*_API_KEY`` env.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database.repositories import credential_repository
from services.api.auth.api_key import require_api_key
from services.api.schemas import (
    ProviderKeyUpdate,
    ProviderStatus,
    ProviderStatusList,
)
from services.model_router.providers import PROVIDERS, base_url_for, credential_for

router = APIRouter(
    prefix="/settings/providers",
    tags=["settings"],
    dependencies=[Depends(require_api_key)],
)


def get_session(request: Request) -> Iterator[Session]:
    """Yield a database session per request and close it afterwards."""
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def mask_key(key: str) -> str:
    """Short display prefix; never enough to reconstruct the key."""
    return key[:4] + "****" if len(key) > 4 else "****"


def _status_for(provider: str, session: Session) -> ProviderStatus:
    """Build the masked status for one provider."""
    spec = PROVIDERS[provider]
    env_key = os.environ.get(spec.api_key_env, "").strip()
    env_base = os.environ.get(f"{provider.upper()}_BASE_URL", "").strip()
    row = credential_repository.get_credential(session, provider)

    if env_key:
        source: str | None = "env"
        key_masked: str | None = mask_key(env_key)
    elif row is not None and row.api_key:
        source = "stored"
        key_masked = mask_key(row.api_key)
    elif env_base:
        source = "env"
        key_masked = None
    elif row is not None and row.base_url:
        source = "stored"
        key_masked = None
    else:
        source = None
        key_masked = None

    return ProviderStatus(
        provider=provider,
        configured=credential_for(provider) is not None,
        source=source,
        key_masked=key_masked,
        base_url=base_url_for(provider),
        stored=row is not None,
    )


@router.get("", response_model=ProviderStatusList)
def list_providers(session: Session = Depends(get_session)) -> ProviderStatusList:
    """Status for every provider; keys appear only as a masked prefix."""
    items = [_status_for(provider, session) for provider in PROVIDERS]
    return ProviderStatusList(items=items, count=len(items))


@router.put("/{provider}", response_model=ProviderStatus)
def store_provider_key(
    provider: str,
    payload: ProviderKeyUpdate,
    session: Session = Depends(get_session),
) -> ProviderStatus:
    """Store a key and/or endpoint manually for one provider."""
    if provider not in PROVIDERS:
        raise HTTPException(
            status_code=422, detail=f"unknown provider: {provider}"
        )

    api_key = payload.api_key.strip() if payload.api_key else ""
    base_url = payload.base_url.strip() if payload.base_url else None

    if not api_key and not base_url:
        raise HTTPException(
            status_code=422, detail="api_key or base_url required"
        )
    if not api_key:
        existing = credential_repository.get_credential(session, provider)
        if existing is not None and existing.api_key:
            api_key = existing.api_key  # endpoint-only update keeps the key
        elif provider == "ollama":
            api_key = "ollama-local"  # local daemon needs no auth
        else:
            raise HTTPException(
                status_code=422, detail="api_key required for this provider"
            )

    credential_repository.upsert_credential(
        session, provider, api_key=api_key, base_url=base_url
    )
    return _status_for(provider, session)


@router.delete("/{provider}", response_model=ProviderStatus)
def delete_provider_key(
    provider: str,
    session: Session = Depends(get_session),
) -> ProviderStatus:
    """Remove the stored key; environment keys are unaffected."""
    if provider not in PROVIDERS:
        raise HTTPException(
            status_code=422, detail=f"unknown provider: {provider}"
        )
    credential_repository.delete_credential(session, provider)
    return _status_for(provider, session)
