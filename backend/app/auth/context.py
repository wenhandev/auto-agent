"""Request-scoped organisation context for multi-tenant routing."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from fastapi import Cookie, Depends, Header, HTTPException
from sqlmodel import Session

from app.auth.authorization import AuthContext
from app.auth.session import extract_bearer_session, verify_session_token
from app.db.session import get_session
from app.settings import settings

_request_auth: ContextVar[Optional[AuthContext]] = ContextVar("_request_auth", default=None)


def set_request_auth(ctx: AuthContext) -> None:
    _request_auth.set(ctx)


def current_auth() -> AuthContext:
    ctx = _request_auth.get()
    if ctx is None:
        raise RuntimeError("auth context not set for this request")
    return ctx


def current_auth_optional() -> Optional[AuthContext]:
    return _request_auth.get()


def current_org_id(session: Session) -> str:
    ctx = _request_auth.get()
    if ctx is not None:
        return ctx.org_id
    from app.services import orgs as org_svc

    return org_svc.get_default_org_id(session)


def _resolve_session_user(
    session: Session,
    token: str,
    x_org_id: Optional[str],
) -> AuthContext:
    from app.db.models import User
    from app.services import orgs as org_svc

    user_id = verify_session_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid session")

    user = session.get(User, user_id)
    if user is None or user.disabled_at is not None:
        raise HTTPException(status_code=401, detail="invalid session")

    if x_org_id:
        org_id = org_svc.resolve_org_id(session, x_org_id)
        role = org_svc.lookup_membership_role(session, user_id, org_id)
        if role is None:
            raise HTTPException(status_code=404, detail="not found")
    else:
        org_id = org_svc.get_default_org_id(session)
        role = org_svc.lookup_membership_role(session, user_id, org_id)
        if role is None:
            raise HTTPException(status_code=403, detail="no organisation membership")

    ctx = AuthContext(org_id=org_id, user_id=user_id, role=role)
    set_request_auth(ctx)
    return ctx


def _resolve_single_user_mode(session: Session, x_org_id: Optional[str]) -> AuthContext:
    from sqlmodel import select

    from app.db.models import User
    from app.services import orgs as org_svc

    org = org_svc.ensure_bootstrap(session)
    org_id = org_svc.resolve_org_id(session, x_org_id) if x_org_id else org.id
    admin_email = (settings.admin_email or "admin@localhost").strip().lower()
    user = session.exec(select(User).where(User.email == admin_email)).first()
    if user is None:
        org_id = org_svc.resolve_org_id(session, x_org_id)
        ctx = AuthContext(org_id=org_id)
        set_request_auth(ctx)
        return ctx

    role = org_svc.lookup_membership_role(session, user.id, org_id)
    if role is None and org_id != org.id:
        raise HTTPException(status_code=404, detail="not found")
    ctx = AuthContext(
        org_id=org_id,
        user_id=user.id,
        role=role or "owner",
    )
    set_request_auth(ctx)
    return ctx


async def get_org_context(
    x_org_id: Optional[str] = Header(default=None, alias="x-org-id"),
    authorization: Optional[str] = Header(default=None),
    session_token: Optional[str] = Cookie(default=None, alias="session_token"),
    session: Session = Depends(get_session),
) -> AuthContext:
    """Resolve org for internal /api/* routes (session, dev header, or default)."""
    from app.services import orgs as org_svc

    bearer = extract_bearer_session(authorization)
    token = bearer or session_token
    if token:
        return _resolve_session_user(session, token, x_org_id)

    if settings.single_user_mode:
        return _resolve_single_user_mode(session, x_org_id)

    try:
        org_id = org_svc.resolve_org_id(session, x_org_id)
    except ValueError as exc:
        raise HTTPException(404, detail="not found") from exc
    ctx = AuthContext(org_id=org_id)
    set_request_auth(ctx)
    return ctx


def auth_context_from_api_key(api_key) -> AuthContext:
    from app.services import orgs as org_svc

    org_id = api_key.org_id or org_svc.get_default_org_id_from_engine()
    ctx = AuthContext(org_id=org_id, api_key_id=api_key.id)
    set_request_auth(ctx)
    return ctx


def effective_org_id(resource_org_id: Optional[str], session: Session) -> str:
    if resource_org_id:
        return resource_org_id
    from app.services import orgs as org_svc

    return org_svc.get_default_org_id(session)


def org_scope_filter(model, org_id: str, session: Session):
    """SQLAlchemy filter: rows in ``org_id``, with NULL treated as default org."""
    from sqlalchemy import or_
    from app.services import orgs as org_svc

    default_org = org_svc.get_default_org_id(session)
    if org_id == default_org:
        return or_(model.org_id == org_id, model.org_id.is_(None))  # type: ignore[union-attr]
    return model.org_id == org_id


def require_org_match(
    resource_org_id: Optional[str], caller_org_id: str, session: Session
) -> None:
    """Cross-org access returns 404 (existence not revealed)."""
    if effective_org_id(resource_org_id, session) != caller_org_id:
        raise HTTPException(404, detail="not found")


__all__ = [
    "AuthContext",
    "auth_context_from_api_key",
    "current_auth",
    "current_auth_optional",
    "current_org_id",
    "effective_org_id",
    "get_org_context",
    "org_scope_filter",
    "require_org_match",
    "set_request_auth",
]
