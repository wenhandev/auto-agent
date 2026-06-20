"""Session authentication routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from sqlmodel import Session, select

from app.auth.context import AuthContext, get_org_context
from app.auth.session import (
    SESSION_COOKIE,
    check_login_rate_limit,
    extract_bearer_session,
    verify_session_token,
)
from app.db.models import User
from app.db.session import get_session
from app.auth.responses import LoginRequest, LoginResponse, MeResponse, build_me
from app.services.auth_login import build_login_response
from app.services import orgs as org_svc
from app.services.orgs import verify_password
from app.settings import settings


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> LoginResponse:
    client_ip = request.client.host if request.client else "unknown"
    check_login_rate_limit(f"login:{client_ip}:{body.email.lower()}")

    if not settings.oauth_password_login_enabled:
        raise HTTPException(status_code=403, detail="password login disabled")

    user = session.exec(
        select(User).where(User.email == body.email.strip().lower())
    ).first()
    if user is None or not user.password_hash:
        raise HTTPException(status_code=401, detail="invalid credentials")
    if user.disabled_at is not None:
        raise HTTPException(status_code=401, detail="invalid credentials")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")

    return build_login_response(session, user, response=response)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
def me(
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE),
    authorization: Optional[str] = Header(default=None),
) -> MeResponse:
    token = extract_bearer_session(authorization) or session_token
    if token:
        user_id = verify_session_token(token)
        if user_id:
            user = session.get(User, user_id)
            if user is not None and user.disabled_at is None:
                role = org_svc.lookup_membership_role(session, user.id, ctx.org_id)
                return build_me(session, user, ctx.org_id, role)

    if ctx.user_id:
        user = session.get(User, ctx.user_id)
        if user is not None:
            return build_me(session, user, ctx.org_id, ctx.role)

    raise HTTPException(status_code=401, detail="not authenticated")


__all__ = ["router"]
