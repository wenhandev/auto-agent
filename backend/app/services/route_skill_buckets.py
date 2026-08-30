"""Route skill bucket aggregation and adopt preview helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from app.db.models import RouteSkill, RouteSkillProposal
from app.services.trajectory_distillation import merge_route_prompts


@dataclass(frozen=True)
class AdoptPreview:
    proposal: RouteSkillProposal
    existing_skill: Optional[RouteSkill]
    merged_prompt: str
    will_create_new: bool


@dataclass(frozen=True)
class SkillBucketRow:
    domain: str
    url_pattern: str
    capability: str
    route_skill_id: Optional[str]
    enabled: bool
    pending_proposals: int
    prompt_preview: str


def _find_existing_skill(session: Session, url_pattern: str) -> Optional[RouteSkill]:
    return session.exec(
        select(RouteSkill)
        .where(
            RouteSkill.url_pattern == url_pattern,
            RouteSkill.scope == "global",
        )
        .order_by(RouteSkill.created_at.asc())  # type: ignore[attr-defined]
    ).first()


def preview_adopt(session: Session, proposal_id: str) -> AdoptPreview:
    proposal = session.get(RouteSkillProposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, detail="route skill proposal not found")
    if proposal.status != "pending":
        raise HTTPException(409, detail=f"proposal is {proposal.status}, not pending")

    existing = _find_existing_skill(session, proposal.url_pattern)
    if existing is not None:
        merged = merge_route_prompts(existing.prompt, proposal.prompt)
        return AdoptPreview(
            proposal=proposal,
            existing_skill=existing,
            merged_prompt=merged,
            will_create_new=False,
        )
    return AdoptPreview(
        proposal=proposal,
        existing_skill=None,
        merged_prompt=proposal.prompt,
        will_create_new=True,
    )


def list_skill_buckets(session: Session) -> list[SkillBucketRow]:
    buckets: dict[str, SkillBucketRow] = {}

    skills = session.exec(
        select(RouteSkill).order_by(RouteSkill.created_at.asc())  # type: ignore[attr-defined]
    ).all()
    for skill in skills:
        domain = _domain_from_pattern(skill.url_pattern)
        buckets[skill.url_pattern] = SkillBucketRow(
            domain=domain,
            url_pattern=skill.url_pattern,
            capability="site-interaction",
            route_skill_id=skill.id,
            enabled=skill.enabled,
            pending_proposals=0,
            prompt_preview=skill.prompt[:240],
        )

    pending = session.exec(
        select(RouteSkillProposal).where(RouteSkillProposal.status == "pending")
    ).all()
    for proposal in pending:
        existing = buckets.get(proposal.url_pattern)
        if existing is not None:
            buckets[proposal.url_pattern] = SkillBucketRow(
                domain=existing.domain or proposal.domain,
                url_pattern=proposal.url_pattern,
                capability=proposal.capability,
                route_skill_id=existing.route_skill_id,
                enabled=existing.enabled,
                pending_proposals=existing.pending_proposals + 1,
                prompt_preview=existing.prompt_preview or proposal.prompt[:240],
            )
        else:
            buckets[proposal.url_pattern] = SkillBucketRow(
                domain=proposal.domain,
                url_pattern=proposal.url_pattern,
                capability=proposal.capability,
                route_skill_id=None,
                enabled=False,
                pending_proposals=1,
                prompt_preview=proposal.prompt[:240],
            )

    rows = list(buckets.values())
    rows.sort(key=lambda row: (row.domain, row.url_pattern, row.capability))
    return rows


def _domain_from_pattern(url_pattern: str) -> str:
    from app.services.trajectory_distillation import _domain_from_url

    return _domain_from_url(url_pattern)


__all__ = [
    "AdoptPreview",
    "SkillBucketRow",
    "preview_adopt",
    "list_skill_buckets",
]
