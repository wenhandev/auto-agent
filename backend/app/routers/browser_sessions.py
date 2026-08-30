from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session

from app.db.models import BrowserSession
from app.db.session import get_session
from app.schemas_api import (
    BrowserSessionCreate,
    BrowserSessionOut,
    PickElementIn,
    PickElementOut,
    PickerDisableIn,
    PickerEnableIn,
    PickerEnableOut,
    SessionNavigateIn,
    SessionNavigateOut,
    TestSelectorIn,
    TestSelectorOut,
)
from app.services import browser_sessions as session_svc
from app.services import element_picker as picker_svc
from app.services.control_plane_policy import require_edge_execution


router = APIRouter(prefix="/api/browser-sessions", tags=["browser-sessions"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_out(row: BrowserSession) -> BrowserSessionOut:
    now = _utcnow()
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    seconds_left = max(0, int((expires_at - now).total_seconds()))
    metadata: dict[str, Any] = {}
    if getattr(row, "provider_metadata_json", None):
        try:
            parsed = json.loads(row.provider_metadata_json)  # type: ignore[arg-type]
            if isinstance(parsed, dict):
                metadata = parsed
        except Exception:
            metadata = {}
    return BrowserSessionOut(
        id=row.id,
        profile_id=row.profile_id,
        status=row.status,  # type: ignore[arg-type]
        started_at=row.started_at,
        expires_at=row.expires_at,
        last_activity_at=row.last_activity_at,
        seconds_until_expiry=seconds_left if row.status == "live" else None,
        provider_id=getattr(row, "provider_id", None) or "local_playwright",
        provider_metadata=metadata,
    )


@router.get("", response_model=list[BrowserSessionOut])
def list_browser_sessions(
    session: Session = Depends(get_session),
) -> list[BrowserSessionOut]:
    rows = session_svc.list_sessions(session)
    return [_to_out(row) for row in rows]


@router.post("", response_model=BrowserSessionOut)
async def create_browser_session(
    body: BrowserSessionCreate,
    session: Session = Depends(get_session),
) -> BrowserSessionOut:
    require_edge_execution("browser_sessions")
    try:
        row = await session_svc.create_session(
            session,
            profile_id=body.profile_id,
            provider_id=body.provider_id,
            provider_config=body.provider_config,
        )
    except session_svc.MaxLiveSessionsError as exc:
        raise HTTPException(429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    return _to_out(row)


@router.get("/{session_id}", response_model=BrowserSessionOut)
def get_browser_session(
    session_id: str, session: Session = Depends(get_session)
) -> BrowserSessionOut:
    row = session_svc.get_session_row(session_id, session)
    if row is None:
        raise HTTPException(404, detail="browser session not found")
    return _to_out(row)


@router.get("/{session_id}/memory")
def get_browser_session_memory(
    session_id: str,
    session: Session = Depends(get_session),
) -> dict:
    try:
        entries = session_svc.list_memory_entries(session, session_id)
    except session_svc.SessionNotAvailableError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    return {"session_id": session_id, "entries": entries}


@router.post("/{session_id}/memory/clear")
def clear_browser_session_memory(
    session_id: str,
    session: Session = Depends(get_session),
) -> dict:
    require_edge_execution("browser_sessions")
    try:
        entries = session_svc.clear_memory_entries(session, session_id)
    except session_svc.SessionNotAvailableError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    return {"session_id": session_id, "entries": entries}


@router.post("/{session_id}/keep-alive", response_model=BrowserSessionOut)
async def keep_browser_session_alive(
    session_id: str, session: Session = Depends(get_session)
) -> BrowserSessionOut:
    require_edge_execution("browser_sessions")
    try:
        row = await session_svc.keep_alive(session_id, session)
    except session_svc.SessionNotAvailableError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    return _to_out(row)


@router.post("/{session_id}/close", response_model=BrowserSessionOut)
async def close_browser_session(
    session_id: str, session: Session = Depends(get_session)
) -> BrowserSessionOut:
    require_edge_execution("browser_sessions")
    row = session_svc.get_session_row(session_id, session)
    if row is None:
        raise HTTPException(404, detail="browser session not found")
    if row.status != "live":
        return _to_out(row)
    await session_svc.close_session(session_id, status="closed")
    session.refresh(row)
    row = session_svc.get_session_row(session_id, session)
    assert row is not None
    return _to_out(row)


@router.delete("/{session_id}")
async def delete_browser_session(
    session_id: str, session: Session = Depends(get_session)
) -> dict:
    require_edge_execution("browser_sessions")
    row = session_svc.get_session_row(session_id, session)
    if row is None:
        raise HTTPException(404, detail="browser session not found")
    if row.status == "live":
        await session_svc.close_session(session_id, status="closed")
    session.delete(row)
    session.commit()
    return {"ok": True}


def _picker_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, session_svc.SessionNotAvailableError):
        return HTTPException(409, detail=str(exc))
    if isinstance(exc, picker_svc.PickerConflictError):
        return HTTPException(409, detail=str(exc))
    if isinstance(exc, picker_svc.PickerNotAuthorizedError):
        return HTTPException(403, detail=str(exc))
    if isinstance(exc, picker_svc.PickerError):
        return HTTPException(400, detail=str(exc))
    return HTTPException(500, detail=str(exc))


@router.post("/{session_id}/picker/enable", response_model=PickerEnableOut)
async def enable_session_picker(
    session_id: str,
    body: PickerEnableIn,
    session: Session = Depends(get_session),
) -> PickerEnableOut:
    require_edge_execution("browser_sessions")
    try:
        result = await picker_svc.enable_picker(
            session_id, session, mode=body.mode
        )
    except Exception as exc:
        raise _picker_http_error(exc) from exc
    return PickerEnableOut(**result)


@router.post("/{session_id}/picker/disable")
async def disable_session_picker(
    session_id: str,
    body: PickerDisableIn,
    session: Session = Depends(get_session),
) -> dict:
    require_edge_execution("browser_sessions")
    try:
        return await picker_svc.disable_picker(
            session_id, session, picker_token=body.picker_token
        )
    except Exception as exc:
        raise _picker_http_error(exc) from exc


@router.post("/{session_id}/navigate", response_model=SessionNavigateOut)
async def navigate_browser_session(
    session_id: str,
    body: SessionNavigateIn,
    session: Session = Depends(get_session),
) -> SessionNavigateOut:
    require_edge_execution("browser_sessions")
    try:
        result = await picker_svc.navigate_picker(
            session_id,
            session,
            picker_token=body.picker_token,
            url=body.url,
        )
    except Exception as exc:
        raise _picker_http_error(exc) from exc
    return SessionNavigateOut(**result)


@router.get("/{session_id}/screenshot")
async def screenshot_browser_session(
    session_id: str,
    picker_token: str,
    session: Session = Depends(get_session),
) -> Response:
    try:
        data, meta = await picker_svc.screenshot_picker(
            session_id, session, picker_token=picker_token
        )
    except Exception as exc:
        raise _picker_http_error(exc) from exc
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={
            "X-Viewport-Width": str(meta["width"]),
            "X-Viewport-Height": str(meta["height"]),
            "X-Device-Scale-Factor": str(meta["deviceScaleFactor"]),
        },
    )


@router.post("/{session_id}/pick-element", response_model=PickElementOut)
async def pick_browser_session_element(
    session_id: str,
    body: PickElementIn,
    session: Session = Depends(get_session),
) -> PickElementOut:
    require_edge_execution("browser_sessions")
    try:
        result = await picker_svc.pick_element(
            session_id,
            session,
            picker_token=body.picker_token,
            x=body.x,
            y=body.y,
        )
    except Exception as exc:
        raise _picker_http_error(exc) from exc
    if result.get("error"):
        return PickElementOut(error=str(result["error"]))
    return PickElementOut(**result)


@router.post("/{session_id}/test-selector", response_model=TestSelectorOut)
async def test_browser_session_selector(
    session_id: str,
    body: TestSelectorIn,
    session: Session = Depends(get_session),
) -> TestSelectorOut:
    require_edge_execution("browser_sessions")
    try:
        result = await picker_svc.test_selector(
            session_id,
            session,
            picker_token=body.picker_token,
            selector=body.selector,
        )
    except Exception as exc:
        raise _picker_http_error(exc) from exc
    return TestSelectorOut(**result)


__all__ = ["router"]
