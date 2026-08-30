"""Route skill proposal management API."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db.models import RouteSkill, RouteSkillProposal
from app.db.session import get_session
from app.routers.route_skills import _to_out as route_skill_to_out
from app.schemas_api import (
    RouteSkillOut,
    RouteSkillProposalAdoptOut,
    RouteSkillProposalAdoptPreviewOut,
    RouteSkillProposalOut,
)
from app.services.route_skill_buckets import preview_adopt
from app.services import route_skill_proposals as proposal_svc


router = APIRouter(prefix="/api/route-skill-proposals", tags=["route-skill-proposals"])


def _proposal_out(row: RouteSkillProposal) -> RouteSkillProposalOut:
    return RouteSkillProposalOut(
        id=row.id,
        source_type=row.source_type,
        source_id=row.source_id,
        org_id=row.org_id,
        domain=row.domain,
        capability=row.capability,
        url_pattern=row.url_pattern,
        prompt=row.prompt,
        status=row.status,  # type: ignore[arg-type]
        adopted_route_skill_id=row.adopted_route_skill_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[RouteSkillProposalOut])
def list_route_skill_proposals(
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    session: Session = Depends(get_session),
) -> list[RouteSkillProposalOut]:
    rows = proposal_svc.list_proposals(
        session,
        source_type=source_type,
        source_id=source_id,
    )
    return [_proposal_out(row) for row in rows]


@router.get("/{proposal_id}/adopt-preview", response_model=RouteSkillProposalAdoptPreviewOut)
def preview_adopt_route_skill_proposal(
    proposal_id: str,
    session: Session = Depends(get_session),
) -> RouteSkillProposalAdoptPreviewOut:
    try:
        preview = preview_adopt(session, proposal_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return RouteSkillProposalAdoptPreviewOut(
        proposal=_proposal_out(preview.proposal),
        existing_route_skill=(
            route_skill_to_out(preview.existing_skill)
            if preview.existing_skill is not None
            else None
        ),
        merged_prompt=preview.merged_prompt,
        will_create_new=preview.will_create_new,
    )


@router.post("/{proposal_id}/adopt", response_model=RouteSkillProposalAdoptOut)
def adopt_route_skill_proposal(
    proposal_id: str,
    session: Session = Depends(get_session),
) -> RouteSkillProposalAdoptOut:
    try:
        proposal, skill = proposal_svc.adopt_proposal(session, proposal_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return RouteSkillProposalAdoptOut(
        proposal=_proposal_out(proposal),
        route_skill=route_skill_to_out(skill),
    )


@router.post("/{proposal_id}/dismiss", response_model=RouteSkillProposalOut)
def dismiss_route_skill_proposal(
    proposal_id: str,
    session: Session = Depends(get_session),
) -> RouteSkillProposalOut:
    try:
        proposal = proposal_svc.dismiss_proposal(session, proposal_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return _proposal_out(proposal)


__all__ = ["router"]
