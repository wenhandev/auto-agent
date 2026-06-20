"""Shared session login response builder."""

from __future__ import annotations

from fastapi import HTTPException, Response
from sqlmodel import Session, select

from app.auth.session import SESSION_COOKIE, SESSION_TTL_SECONDS, create_session_token
from app.db.models import OrgMembership, User
from app.auth.responses import LoginResponse, build_me
from app.services import orgs as org_svc


def build_login_response(
    session: Session,
    user: User,
    *,
    response: Response | None = None,
) -> LoginResponse:
    if user.disabled_at is not None:
        raise HTTPException(status_code=401, detail="invalid credentials")

    default_org = org_svc.ensure_bootstrap(session)
    role = org_svc.lookup_membership_role(session, user.id, default_org.id)
    org_id = default_org.id
    if role is None:
        membership = session.exec(
            select(OrgMembership)
            .where(OrgMembership.user_id == user.id)
            .order_by(OrgMembership.created_at)  # type: ignore[arg-type]
        ).first()
        if membership is None:
            raise HTTPException(status_code=403, detail="no organisation membership")
        org_id = membership.org_id
        role = membership.role

    token = create_session_token(user.id)
    if response is not None:
        response.set_cookie(
            key=SESSION_COOKIE,
            value=token,
            httponly=True,
            samesite="lax",
            max_age=SESSION_TTL_SECONDS,
            path="/",
        )
    me = build_me(session, user, org_id, role)
    return LoginResponse(token=token, user=me)
