"""Shared FastAPI auth dependencies."""

from __future__ import annotations

from typing import Optional, Union

from fastapi import Cookie, Depends, Header, HTTPException
from sqlmodel import Session

from app.auth.api_key import authenticate_api_key
from app.auth.authorization import AuthContext
from app.auth.context import _resolve_session_user, set_request_auth
from app.auth.session import extract_bearer_session, verify_session_token
from app.db.models import ApiKey
from app.db.session import get_session


async def require_v1_auth(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    session_token: Optional[str] = Cookie(default=None, alias="session_token"),
    x_org_id: Optional[str] = Header(default=None, alias="x-org-id"),
    session: Session = Depends(get_session),
) -> Union[ApiKey, AuthContext]:
    """Accept org-scoped API keys or a session bearer/cookie for /api/v1/*."""
    bearer = extract_bearer_session(authorization)
    bearer = extract_bearer_session(authorization)
    token = bearer or session_token
    if token and verify_session_token(token):
        return _resolve_session_user(session, token, x_org_id)
    try:
        return authenticate_api_key(session, authorization, x_api_key)
    except HTTPException as exc:
        if exc.status_code == 401 and token:
            raise HTTPException(status_code=401, detail="invalid session") from exc
        raise


async def require_v1_auth_or_bootstrap(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    session_token: Optional[str] = Cookie(default=None, alias="session_token"),
    x_org_id: Optional[str] = Header(default=None, alias="x-org-id"),
    session: Session = Depends(get_session),
) -> Optional[Union[ApiKey, AuthContext]]:
    from app.services import api_keys as api_key_svc

    if api_key_svc.count_active_keys(session) == 0:
        from app.services import orgs as org_svc

        org_id = org_svc.resolve_org_id(session, x_org_id)
        ctx = AuthContext(org_id=org_id)
        set_request_auth(ctx)
        return None
    return await require_v1_auth(
        authorization,
        x_api_key,
        session_token,
        x_org_id,
        session,
    )


__all__ = ["require_v1_auth", "require_v1_auth_or_bootstrap"]
