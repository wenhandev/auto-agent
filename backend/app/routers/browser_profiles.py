from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db.models import BrowserProfile, Run
from app.schemas_api import (
    BrowserProfileCreate,
    BrowserProfileOut,
    BrowserProfileUpdate,
    ViewportSpec,
)
from app.services import browser_profiles as profile_svc
from app.tools import browser as browser_tools
from app.db.session import get_session


router = APIRouter(prefix="/api/browser-profiles", tags=["browser-profiles"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _viewport_out(profile: BrowserProfile) -> Optional[ViewportSpec]:
    vp = profile_svc.parse_viewport(profile)
    if vp is None:
        return None
    return ViewportSpec(width=vp["width"], height=vp["height"])


def _to_out(profile: BrowserProfile) -> BrowserProfileOut:
    return BrowserProfileOut(
        id=profile.id,
        name=profile.name,
        user_agent=profile.user_agent,
        viewport=_viewport_out(profile),
        persist_cookies=profile.persist_cookies,
        persist_local_storage=profile.persist_local_storage,
        has_storage_state=profile_svc.has_storage_state(profile.id),
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        last_used_at=profile.last_used_at,
    )


@router.get("", response_model=list[BrowserProfileOut])
def list_browser_profiles(
    session: Session = Depends(get_session),
) -> list[BrowserProfileOut]:
    rows = session.exec(
        select(BrowserProfile).order_by(BrowserProfile.updated_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [_to_out(row) for row in rows]


@router.post("", response_model=BrowserProfileOut)
def create_browser_profile(
    body: BrowserProfileCreate, session: Session = Depends(get_session)
) -> BrowserProfileOut:
    existing = session.exec(
        select(BrowserProfile).where(BrowserProfile.name == body.name)
    ).first()
    if existing is not None:
        raise HTTPException(409, detail="browser profile name already exists")
    viewport = body.viewport.model_dump() if body.viewport is not None else None
    profile = profile_svc.create_profile_row(
        name=body.name,
        user_agent=body.user_agent,
        viewport=viewport,
        persist_cookies=body.persist_cookies,
        persist_local_storage=body.persist_local_storage,
        session=session,
    )
    return _to_out(profile)


@router.get("/{profile_id}", response_model=BrowserProfileOut)
def get_browser_profile(
    profile_id: str, session: Session = Depends(get_session)
) -> BrowserProfileOut:
    profile = session.get(BrowserProfile, profile_id)
    if profile is None:
        raise HTTPException(404, detail="browser profile not found")
    return _to_out(profile)


@router.patch("/{profile_id}", response_model=BrowserProfileOut)
@router.put("/{profile_id}", response_model=BrowserProfileOut)
def update_browser_profile(
    profile_id: str,
    body: BrowserProfileUpdate,
    session: Session = Depends(get_session),
) -> BrowserProfileOut:
    profile = session.get(BrowserProfile, profile_id)
    if profile is None:
        raise HTTPException(404, detail="browser profile not found")
    if body.name is not None and body.name != profile.name:
        clash = session.exec(
            select(BrowserProfile).where(BrowserProfile.name == body.name)
        ).first()
        if clash is not None:
            raise HTTPException(409, detail="browser profile name already exists")
        profile.name = body.name
    if body.user_agent is not None:
        profile.user_agent = body.user_agent
    if body.viewport is not None:
        profile.viewport_json = json.dumps(body.viewport.model_dump(), ensure_ascii=False)
    if body.persist_cookies is not None:
        profile.persist_cookies = body.persist_cookies
    if body.persist_local_storage is not None:
        profile.persist_local_storage = body.persist_local_storage
    profile.updated_at = _utcnow()
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return _to_out(profile)


@router.delete("/{profile_id}")
def delete_browser_profile(
    profile_id: str, session: Session = Depends(get_session)
) -> dict:
    profile = session.get(BrowserProfile, profile_id)
    if profile is None:
        raise HTTPException(404, detail="browser profile not found")
    profile_svc.delete_profile_files(profile_id)
    session.delete(profile)
    session.commit()
    return {"ok": True}


@router.post("/{profile_id}/capture-from-run/{run_id}", response_model=BrowserProfileOut)
async def capture_profile_from_run(
    profile_id: str,
    run_id: str,
    session: Session = Depends(get_session),
) -> BrowserProfileOut:
    profile = session.get(BrowserProfile, profile_id)
    if profile is None:
        raise HTTPException(404, detail="browser profile not found")
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, detail="run not found")
    context = browser_tools.get_active_context()
    if context is None:
        raise HTTPException(
            409,
            detail="no active browser context for this process; run must be in progress",
        )
    await profile_svc.save_from_context(profile_id, context, session=session)
    session.refresh(profile)
    return _to_out(profile)


__all__ = ["router"]
