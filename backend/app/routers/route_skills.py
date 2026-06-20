"""Route skill management API (minimal backend surface for UI/SDK)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db.models import RouteSkill
from app.db.session import get_session
from app.schemas_api import RouteSkillCreate, RouteSkillOut, RouteSkillUpdate


router = APIRouter(prefix="/api/route-skills", tags=["route-skills"])


def _to_out(row: RouteSkill) -> RouteSkillOut:
    allowed_tools: list[str] = []
    if row.allowed_tools_json:
        try:
            parsed = json.loads(row.allowed_tools_json)
            if isinstance(parsed, list):
                allowed_tools = [str(item) for item in parsed]
        except Exception:
            allowed_tools = []
    return RouteSkillOut(
        id=row.id,
        scope=row.scope,
        org_id=row.org_id,
        workflow_id=row.workflow_id,
        url_pattern=row.url_pattern,
        prompt=row.prompt,
        allowed_tools=allowed_tools,
        priority=row.priority,
        enabled=row.enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[RouteSkillOut])
def list_route_skills(session: Session = Depends(get_session)) -> list[RouteSkillOut]:
    rows = session.exec(
        select(RouteSkill).order_by(RouteSkill.priority.desc(), RouteSkill.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [_to_out(row) for row in rows]


@router.post("", response_model=RouteSkillOut)
def create_route_skill(
    body: RouteSkillCreate,
    session: Session = Depends(get_session),
) -> RouteSkillOut:
    now = datetime.now(timezone.utc)
    row = RouteSkill(
        scope=body.scope,
        org_id=body.org_id,
        workflow_id=body.workflow_id,
        url_pattern=body.url_pattern,
        prompt=body.prompt,
        allowed_tools_json=json.dumps(body.allowed_tools or [], ensure_ascii=False),
        priority=body.priority,
        enabled=body.enabled,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row)


@router.get("/{skill_id}", response_model=RouteSkillOut)
def get_route_skill(
    skill_id: str,
    session: Session = Depends(get_session),
) -> RouteSkillOut:
    row = session.get(RouteSkill, skill_id)
    if row is None:
        raise HTTPException(404, detail="route skill not found")
    return _to_out(row)


@router.patch("/{skill_id}", response_model=RouteSkillOut)
def update_route_skill(
    skill_id: str,
    body: RouteSkillUpdate,
    session: Session = Depends(get_session),
) -> RouteSkillOut:
    row = session.get(RouteSkill, skill_id)
    if row is None:
        raise HTTPException(404, detail="route skill not found")
    if body.prompt is not None:
        row.prompt = body.prompt
    if body.allowed_tools is not None:
        row.allowed_tools_json = json.dumps(body.allowed_tools, ensure_ascii=False)
    if body.priority is not None:
        row.priority = body.priority
    if body.enabled is not None:
        row.enabled = body.enabled
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_out(row)


@router.delete("/{skill_id}")
def delete_route_skill(
    skill_id: str,
    session: Session = Depends(get_session),
) -> dict:
    row = session.get(RouteSkill, skill_id)
    if row is None:
        raise HTTPException(404, detail="route skill not found")
    session.delete(row)
    session.commit()
    return {"ok": True}


__all__ = ["router"]
