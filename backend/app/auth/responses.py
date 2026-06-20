"""Session auth response schemas and builders."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from app.db.models import Organization, OrgMembership, User


class OrgMembershipOut(BaseModel):
    org_id: str
    org_name: str
    role: str


class MeResponse(BaseModel):
    id: str
    email: str
    name: Optional[str]
    current_org_id: str
    role: Optional[str]
    is_platform_admin: bool = False
    memberships: list[OrgMembershipOut]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    token: str
    user: MeResponse


def memberships_for_user(session: Session, user_id: str) -> list[OrgMembershipOut]:
    rows = session.exec(
        select(OrgMembership, Organization)
        .where(OrgMembership.user_id == user_id)
        .join(Organization, Organization.id == OrgMembership.org_id)
        .order_by(Organization.name)  # type: ignore[arg-type]
    ).all()
    items: list[OrgMembershipOut] = []
    for membership, org in rows:
        items.append(
            OrgMembershipOut(
                org_id=org.id,
                org_name=org.name,
                role=membership.role,
            )
        )
    return items


def build_me(
    session: Session,
    user: User,
    org_id: str,
    role: Optional[str],
) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        current_org_id=org_id,
        role=role,
        is_platform_admin=bool(user.is_platform_admin),
        memberships=memberships_for_user(session, user.id),
    )
