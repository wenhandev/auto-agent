"""Adopt and dismiss distilled route skill proposals."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlmodel import Session, select

from app.db.models import RouteSkill, RouteSkillProposal
from app.services.route_skill_buckets import _find_existing_skill
from app.services.trajectory_distillation import merge_route_prompts


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def list_proposals(
    session: Session,
    *,
    source_type: str | None = None,
    source_id: str | None = None,
) -> list[RouteSkillProposal]:
    stmt = select(RouteSkillProposal)
    if source_type is not None:
        stmt = stmt.where(RouteSkillProposal.source_type == source_type)
    if source_id is not None:
        stmt = stmt.where(RouteSkillProposal.source_id == source_id)
    rows = session.exec(
        stmt.order_by(RouteSkillProposal.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [
        row
        for row in rows
        if row.status in ("pending", "adopted", "dismissed")
    ]


def adopt_proposal(session: Session, proposal_id: str) -> tuple[RouteSkillProposal, RouteSkill]:
    proposal = session.get(RouteSkillProposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, detail="route skill proposal not found")
    if proposal.status != "pending":
        raise HTTPException(409, detail=f"proposal is {proposal.status}, not pending")

    now = _utcnow()
    existing = _find_existing_skill(session, proposal.url_pattern)

    if existing is not None:
        existing.prompt = merge_route_prompts(existing.prompt, proposal.prompt)
        existing.updated_at = now
        session.add(existing)
        skill = existing
    else:
        skill = RouteSkill(
            scope="global",
            org_id=proposal.org_id,
            url_pattern=proposal.url_pattern,
            prompt=proposal.prompt,
            allowed_tools_json=json.dumps([], ensure_ascii=False),
            priority=0,
            enabled=False,
            created_at=now,
            updated_at=now,
        )
        session.add(skill)

    proposal.status = "adopted"
    proposal.adopted_route_skill_id = skill.id
    proposal.updated_at = now
    session.add(proposal)
    session.commit()
    session.refresh(proposal)
    session.refresh(skill)
    return proposal, skill


def dismiss_proposal(session: Session, proposal_id: str) -> RouteSkillProposal:
    proposal = session.get(RouteSkillProposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, detail="route skill proposal not found")
    if proposal.status != "pending":
        raise HTTPException(409, detail=f"proposal is {proposal.status}, not pending")
    proposal.status = "dismissed"
    proposal.updated_at = _utcnow()
    session.add(proposal)
    session.commit()
    session.refresh(proposal)
    return proposal


__all__ = ["list_proposals", "adopt_proposal", "dismiss_proposal"]
