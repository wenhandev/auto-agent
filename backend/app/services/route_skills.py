"""URL-pattern route skills for autonomous and hybrid browser agents."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from sqlmodel import Session, select

from app.db.models import RouteSkill
from app.services.selector_cache import normalize_url


@dataclass(frozen=True)
class RouteSkillContext:
    skill_ids: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    allowed_tools: Optional[frozenset[str]] = None


def _parse_allowed_tools(raw: Optional[str]) -> Optional[frozenset[str]]:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    if not isinstance(parsed, list):
        return None
    values = {str(item) for item in parsed if str(item)}
    return frozenset(values) if values else None


def match_route_skills(
    session: Session,
    url: str,
    *,
    org_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
) -> list[RouteSkill]:
    pattern = normalize_url(url)
    stmt = select(RouteSkill).where(
        RouteSkill.enabled == True,  # noqa: E712
        RouteSkill.url_pattern == pattern,
    )
    rows = list(session.exec(stmt).all())
    filtered: list[RouteSkill] = []
    for row in rows:
        if row.workflow_id is not None and row.workflow_id != workflow_id:
            continue
        if row.org_id is not None and row.org_id != org_id:
            continue
        filtered.append(row)
    return sorted(filtered, key=lambda row: (-row.priority, row.created_at, row.id))


def build_route_context(
    session: Session,
    url: str,
    *,
    task_allowed_tools: frozenset[str],
    org_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
) -> RouteSkillContext:
    skills = match_route_skills(
        session,
        url,
        org_id=org_id,
        workflow_id=workflow_id,
    )
    allowed = task_allowed_tools
    for skill in skills:
        skill_tools = _parse_allowed_tools(skill.allowed_tools_json)
        if skill_tools is not None:
            allowed = allowed.intersection(skill_tools)
    return RouteSkillContext(
        skill_ids=[skill.id for skill in skills],
        prompts=[skill.prompt for skill in skills],
        allowed_tools=allowed,
    )


__all__ = [
    "RouteSkillContext",
    "build_route_context",
    "match_route_skills",
]
