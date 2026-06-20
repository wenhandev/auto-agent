"""Platform admin console API (cross-org)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from app.auth.platform_admin import require_platform_admin
from app.auth.responses import OrgMembershipOut, memberships_for_user
from app.db.models import OAuthDomainRule, Organization, OrgMembership, User
from app.db.session import get_session
from app.services.orgs import ORG_ROLES, hash_password
from app.settings import settings


router = APIRouter(prefix="/api/admin", tags=["admin"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrgOut(BaseModel):
    id: str
    name: str
    desktop_client_policy: str
    created_at: datetime


class OrgCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    desktop_client_policy: str = Field(default="approval_required")


class OrgUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    desktop_client_policy: Optional[str] = None


class AdminUserOut(BaseModel):
    id: str
    email: str
    name: Optional[str]
    is_platform_admin: bool
    disabled_at: Optional[datetime]
    created_at: datetime
    memberships: list[OrgMembershipOut]


class AdminUserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3)
    name: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=8)
    org_id: str
    role: str = Field(default="member")
    is_platform_admin: bool = False


class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    is_platform_admin: Optional[bool] = None
    disabled: Optional[bool] = None


class PasswordReset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=8)


class DomainRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str = Field(min_length=1, max_length=255)
    org_id: str = Field(min_length=1)
    default_role: str = Field(default="member", min_length=1)


class DomainRuleOut(BaseModel):
    id: str
    domain: str
    org_id: str
    default_role: str
    created_at: datetime


def _org_out(org: Organization) -> OrgOut:
    return OrgOut(
        id=org.id,
        name=org.name,
        desktop_client_policy=org.desktop_client_policy,
        created_at=org.created_at,
    )


def _user_out(session: Session, user: User) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        is_platform_admin=bool(user.is_platform_admin),
        disabled_at=user.disabled_at,
        created_at=user.created_at,
        memberships=memberships_for_user(session, user.id),
    )


def _get_user(session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return user


@router.get("/orgs")
def list_orgs(
    session: Session = Depends(get_session),
    _admin: User = Depends(require_platform_admin),
) -> dict:
    rows = session.exec(
        select(Organization).order_by(Organization.name)  # type: ignore[arg-type]
    ).all()
    return {"items": [_org_out(org).model_dump(mode="json") for org in rows]}


@router.post("/orgs", status_code=status.HTTP_201_CREATED)
def create_org(
    body: OrgCreate,
    session: Session = Depends(get_session),
    _admin: User = Depends(require_platform_admin),
) -> dict:
    if body.desktop_client_policy not in ("disabled", "approval_required", "open"):
        raise HTTPException(status_code=400, detail="invalid desktop_client_policy")
    org = Organization(
        name=body.name.strip(),
        desktop_client_policy=body.desktop_client_policy,
        created_at=_utcnow(),
    )
    session.add(org)
    session.commit()
    session.refresh(org)
    return _org_out(org).model_dump(mode="json")


@router.patch("/orgs/{org_id}")
def update_org(
    org_id: str,
    body: OrgUpdate,
    session: Session = Depends(get_session),
    _admin: User = Depends(require_platform_admin),
) -> dict:
    org = session.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="organization not found")
    if body.name is not None:
        org.name = body.name.strip()
    if body.desktop_client_policy is not None:
        if body.desktop_client_policy not in ("disabled", "approval_required", "open"):
            raise HTTPException(status_code=400, detail="invalid desktop_client_policy")
        org.desktop_client_policy = body.desktop_client_policy
    session.add(org)
    session.commit()
    session.refresh(org)
    return _org_out(org).model_dump(mode="json")


@router.get("/users")
def list_users(
    session: Session = Depends(get_session),
    _admin: User = Depends(require_platform_admin),
    org_id: Optional[str] = Query(default=None),
    email: Optional[str] = Query(default=None),
) -> dict:
    stmt = select(User).order_by(User.email)  # type: ignore[arg-type]
    if email:
        stmt = stmt.where(User.email == email.strip().lower())
    users = list(session.exec(stmt).all())
    if org_id:
        member_ids = {
            row.user_id
            for row in session.exec(
                select(OrgMembership).where(OrgMembership.org_id == org_id)
            ).all()
        }
        users = [user for user in users if user.id in member_ids]
    return {"items": [_user_out(session, user).model_dump(mode="json") for user in users]}


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    body: AdminUserCreate,
    session: Session = Depends(get_session),
    _admin: User = Depends(require_platform_admin),
) -> dict:
    if body.role not in ORG_ROLES:
        raise HTTPException(status_code=400, detail="invalid role")
    if body.role == "owner":
        raise HTTPException(status_code=400, detail="cannot assign owner via admin create")

    org = session.get(Organization, body.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="organization not found")

    email = body.email.strip().lower()
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="email already in use")

    user = User(
        email=email,
        name=body.name,
        password_hash=hash_password(body.password) if body.password else None,
        is_platform_admin=body.is_platform_admin,
        created_at=_utcnow(),
    )
    session.add(user)
    session.flush()
    session.add(
        OrgMembership(
            user_id=user.id,
            org_id=body.org_id,
            role=body.role,
            created_at=_utcnow(),
        )
    )
    session.commit()
    session.refresh(user)
    return _user_out(session, user).model_dump(mode="json")


@router.patch("/users/{user_id}")
def update_user(
    user_id: str,
    body: AdminUserUpdate,
    session: Session = Depends(get_session),
    admin: User = Depends(require_platform_admin),
) -> dict:
    user = _get_user(session, user_id)
    if body.is_platform_admin is not None:
        if user_id == admin.id and body.is_platform_admin is False:
            raise HTTPException(status_code=409, detail="cannot revoke own platform admin")
        user.is_platform_admin = body.is_platform_admin
    if body.name is not None:
        user.name = body.name
    if body.disabled is not None:
        user.disabled_at = _utcnow() if body.disabled else None
    session.add(user)
    session.commit()
    session.refresh(user)
    return _user_out(session, user).model_dump(mode="json")


@router.post("/users/{user_id}/password")
def reset_user_password(
    user_id: str,
    body: PasswordReset,
    session: Session = Depends(get_session),
    _admin: User = Depends(require_platform_admin),
) -> dict:
    user = _get_user(session, user_id)
    user.password_hash = hash_password(body.password)
    session.add(user)
    session.commit()
    return {"id": user_id, "status": "password_reset"}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str,
    session: Session = Depends(get_session),
    admin: User = Depends(require_platform_admin),
) -> None:
    if user_id == admin.id:
        raise HTTPException(status_code=409, detail="cannot delete own account")
    user = _get_user(session, user_id)
    for membership in session.exec(
        select(OrgMembership).where(OrgMembership.user_id == user.id)
    ).all():
        session.delete(membership)
    session.delete(user)
    session.commit()


@router.get("/auth/settings")
def get_auth_settings(
    _admin: User = Depends(require_platform_admin),
) -> dict:
    return {
        "providers": {
            "google": bool(
                settings.oauth_google_client_id and settings.oauth_google_client_secret
            ),
        },
        "signup_policy": settings.oauth_signup_policy,
        "password_login_enabled": settings.oauth_password_login_enabled,
    }


@router.get("/auth/domain-rules")
def list_domain_rules(
    session: Session = Depends(get_session),
    _admin: User = Depends(require_platform_admin),
) -> dict:
    rows = session.exec(
        select(OAuthDomainRule).order_by(OAuthDomainRule.domain)  # type: ignore[arg-type]
    ).all()
    items = [
        DomainRuleOut(
            id=row.id,
            domain=row.domain,
            org_id=row.org_id,
            default_role=row.default_role,
            created_at=row.created_at,
        ).model_dump(mode="json")
        for row in rows
    ]
    return {"items": items}


@router.post("/auth/domain-rules", status_code=status.HTTP_201_CREATED)
def create_domain_rule(
    body: DomainRuleCreate,
    session: Session = Depends(get_session),
    _admin: User = Depends(require_platform_admin),
) -> dict:
    if body.default_role not in ORG_ROLES or body.default_role == "owner":
        raise HTTPException(status_code=400, detail="invalid default_role")
    org = session.get(Organization, body.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="organization not found")
    domain = body.domain.strip().lower()
    existing = session.exec(
        select(OAuthDomainRule).where(OAuthDomainRule.domain == domain)
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="domain rule already exists")
    rule = OAuthDomainRule(
        domain=domain,
        org_id=body.org_id,
        default_role=body.default_role,
        created_at=_utcnow(),
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return DomainRuleOut(
        id=rule.id,
        domain=rule.domain,
        org_id=rule.org_id,
        default_role=rule.default_role,
        created_at=rule.created_at,
    ).model_dump(mode="json")


@router.delete("/auth/domain-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_domain_rule(
    rule_id: str,
    session: Session = Depends(get_session),
    _admin: User = Depends(require_platform_admin),
) -> None:
    rule = session.get(OAuthDomainRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="domain rule not found")
    session.delete(rule)
    session.commit()


__all__ = ["router"]
