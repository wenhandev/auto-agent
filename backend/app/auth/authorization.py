"""Central authorization: role hierarchy and workflow visibility."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_
from sqlmodel import Session

from app.db.models import Workflow

ROLE_RANK = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}
WORKFLOW_VISIBILITY = frozenset({"private", "org"})


@dataclass(frozen=True)
class AuthContext:
    org_id: str
    user_id: Optional[str] = None
    role: Optional[str] = None
    api_key_id: Optional[str] = None


def effective_role(ctx: AuthContext) -> str:
    if ctx.role:
        return ctx.role
    if ctx.api_key_id:
        return "admin"
    if ctx.user_id:
        return "member"
    return "member"


def require_min_role(ctx: AuthContext, min_role: str) -> None:
    if min_role not in ROLE_RANK:
        raise ValueError(f"unknown role {min_role!r}")
    if ROLE_RANK[effective_role(ctx)] < ROLE_RANK[min_role]:
        raise HTTPException(status_code=403, detail="insufficient permissions")


def workflow_visible_to_caller(
    workflow: Workflow,
    *,
    user_id: Optional[str],
    role: str,
) -> bool:
    visibility = workflow.visibility or "org"
    if visibility == "org":
        return True
    if visibility == "private":
        if workflow.created_by and user_id and workflow.created_by == user_id:
            return True
        if role in ("admin", "owner"):
            return True
        return False
    return True


def workflow_visibility_filter(
    model: type[Workflow],
    *,
    user_id: Optional[str],
    role: str,
):
    org_visible = or_(model.visibility == "org", model.visibility.is_(None))  # type: ignore[union-attr]
    if user_id:
        private_mine = (model.visibility == "private") & (model.created_by == user_id)  # type: ignore[operator]
        if role in ("admin", "owner"):
            return or_(org_visible, model.visibility == "private")  # type: ignore[union-attr]
        return or_(org_visible, private_mine)
    return org_visible


def require_workflow_visible(
    workflow: Workflow,
    ctx: AuthContext,
) -> None:
    if not workflow_visible_to_caller(
        workflow,
        user_id=ctx.user_id,
        role=effective_role(ctx),
    ):
        raise HTTPException(status_code=404, detail="not found")


__all__ = [
    "ROLE_RANK",
    "WORKFLOW_VISIBILITY",
    "effective_role",
    "require_min_role",
    "require_workflow_visible",
    "workflow_visibility_filter",
    "workflow_visible_to_caller",
]
