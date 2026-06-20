"""Organisation membership management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from app.auth.authorization import require_min_role
from app.auth.context import AuthContext, get_org_context, require_org_match
from app.db.models import Organization, OrgMembership, User
from app.db.session import get_session
from app.schemas_api import OrgSettingsOut, OrgSettingsUpdate
from app.services import workers as worker_svc
from app.services.orgs import ORG_ROLES, hash_password


router = APIRouter(prefix="/api/orgs", tags=["orgs"])


class MemberOut(BaseModel):
    user_id: str
    email: str
    name: Optional[str]
    role: str
    created_at: datetime


class MemberInvite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3)
    role: str = Field(default="member")
    name: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=8)


class MemberRoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _member_out(session: Session, membership: OrgMembership) -> MemberOut:
    user = session.get(User, membership.user_id)
    if user is None:
        raise HTTPException(404, detail="user not found")
    return MemberOut(
        user_id=user.id,
        email=user.email,
        name=user.name,
        role=membership.role,
        created_at=membership.created_at,
    )


@router.get("/{org_id}/members", response_model=list[MemberOut])
def list_members(
    org_id: str,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> list[MemberOut]:
    require_org_match(org_id, ctx.org_id, session)
    org = session.get(Organization, org_id)
    if org is None:
        raise HTTPException(404, detail="not found")
    rows = session.exec(
        select(OrgMembership)
        .where(OrgMembership.org_id == org_id)
        .order_by(OrgMembership.created_at)  # type: ignore[arg-type]
    ).all()
    return [_member_out(session, row) for row in rows]


@router.get("/{org_id}/settings", response_model=OrgSettingsOut)
def get_org_settings(
    org_id: str,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> OrgSettingsOut:
    require_org_match(org_id, ctx.org_id, session)
    org = session.get(Organization, org_id)
    if org is None:
        raise HTTPException(404, detail="not found")
    return OrgSettingsOut(
        org_id=org.id,
        desktop_client_policy=worker_svc.effective_desktop_client_policy(org),
    )


@router.patch("/{org_id}/settings", response_model=OrgSettingsOut)
def update_org_settings(
    org_id: str,
    body: OrgSettingsUpdate,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> OrgSettingsOut:
    require_org_match(org_id, ctx.org_id, session)
    require_min_role(ctx, "admin")
    org = session.get(Organization, org_id)
    if org is None:
        raise HTTPException(404, detail="not found")
    org.desktop_client_policy = body.desktop_client_policy
    session.add(org)
    session.commit()
    session.refresh(org)
    return OrgSettingsOut(
        org_id=org.id,
        desktop_client_policy=worker_svc.effective_desktop_client_policy(org),
    )


@router.post("/{org_id}/members", response_model=MemberOut, status_code=201)
def invite_member(
    org_id: str,
    body: MemberInvite,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> MemberOut:
    require_org_match(org_id, ctx.org_id, session)
    require_min_role(ctx, "admin")
    if body.role not in ORG_ROLES:
        raise HTTPException(400, detail="invalid role")
    if body.role == "owner":
        raise HTTPException(400, detail="cannot assign owner via invite")

    org = session.get(Organization, org_id)
    if org is None:
        raise HTTPException(404, detail="not found")

    email = body.email.strip().lower()
    user = session.exec(select(User).where(User.email == email)).first()
    if user is None:
        if not body.password:
            raise HTTPException(400, detail="password required for new user")
        user = User(
            email=email,
            name=body.name,
            password_hash=hash_password(body.password),
            created_at=_utcnow(),
        )
        session.add(user)
        session.flush()

    existing = session.exec(
        select(OrgMembership).where(
            OrgMembership.user_id == user.id,
            OrgMembership.org_id == org_id,
        )
    ).first()
    if existing is not None:
        raise HTTPException(409, detail="user already a member")

    membership = OrgMembership(
        user_id=user.id,
        org_id=org_id,
        role=body.role,
        created_at=_utcnow(),
    )
    session.add(membership)
    session.commit()
    session.refresh(membership)
    return _member_out(session, membership)


@router.patch("/{org_id}/members/{user_id}", response_model=MemberOut)
def update_member_role(
    org_id: str,
    user_id: str,
    body: MemberRoleUpdate,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> MemberOut:
    require_org_match(org_id, ctx.org_id, session)
    require_min_role(ctx, "admin")
    if body.role not in ORG_ROLES:
        raise HTTPException(400, detail="invalid role")
    if body.role == "owner":
        raise HTTPException(400, detail="cannot assign owner via update")

    membership = session.exec(
        select(OrgMembership).where(
            OrgMembership.user_id == user_id,
            OrgMembership.org_id == org_id,
        )
    ).first()
    if membership is None:
        raise HTTPException(404, detail="not found")
    if membership.role == "owner":
        raise HTTPException(400, detail="cannot change owner role")

    membership.role = body.role
    session.add(membership)
    session.commit()
    session.refresh(membership)
    return _member_out(session, membership)


@router.delete("/{org_id}/members/{user_id}", status_code=204)
def remove_member(
    org_id: str,
    user_id: str,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> None:
    require_org_match(org_id, ctx.org_id, session)
    require_min_role(ctx, "admin")

    membership = session.exec(
        select(OrgMembership).where(
            OrgMembership.user_id == user_id,
            OrgMembership.org_id == org_id,
        )
    ).first()
    if membership is None:
        raise HTTPException(404, detail="not found")
    if membership.role == "owner":
        raise HTTPException(400, detail="cannot remove owner")

    session.delete(membership)
    session.commit()


__all__ = ["router"]
