"""Browser session element picker operations."""

from __future__ import annotations

import secrets
import uuid
from typing import Any, Optional

from playwright.async_api import Page
from sqlmodel import Session

from app.services import browser_sessions as session_svc
from app.services.selector_builder import resolve_element_at_point, test_selector_on_page


class PickerError(Exception):
    """Picker operation failed."""


class PickerNotAuthorizedError(PickerError):
    """Invalid or missing picker token."""


class PickerConflictError(PickerError):
    """Session busy with run or another picker."""


def _require_live_entry(session_id: str) -> session_svc._LiveEntry:
    entry = session_svc._live.get(session_id)
    if entry is None:
        raise session_svc.SessionNotAvailableError(
            f"browser session {session_id!r} is not active in this process"
        )
    return entry


def _validate_token(entry: session_svc._LiveEntry, token: Optional[str]) -> None:
    if not entry.picker_token or not token or not secrets.compare_digest(
        entry.picker_token, token
    ):
        raise PickerNotAuthorizedError("invalid or missing picker token")


async def enable_picker(
    session_id: str,
    db: Session,
    *,
    mode: str = "coordinate",
) -> dict[str, Any]:
    row = session_svc.get_session_row(session_id, db)
    if row is None:
        raise session_svc.SessionNotAvailableError(
            f"browser session {session_id!r} not found"
        )
    if row.status != "live":
        raise session_svc.SessionNotAvailableError(
            f"browser session {session_id!r} is not live"
        )
    async with session_svc._lock:
        entry = _require_live_entry(session_id)
        if entry.attached_run_id:
            raise PickerConflictError(
                f"browser session {session_id!r} is attached to a run"
            )
        if entry.picker_token:
            raise PickerConflictError(
                f"browser session {session_id!r} already has picker active"
            )
        token = uuid.uuid4().hex
        entry.picker_token = token
        entry.picker_mode = mode if mode in ("coordinate", "injected") else "coordinate"
    session_svc.touch_activity(session_id)
    return {"picker_token": token, "mode": entry.picker_mode}


async def disable_picker(
    session_id: str,
    db: Session,
    *,
    picker_token: str,
) -> dict[str, Any]:
    row = session_svc.get_session_row(session_id, db)
    if row is None:
        raise session_svc.SessionNotAvailableError(
            f"browser session {session_id!r} not found"
        )
    async with session_svc._lock:
        entry = session_svc._live.get(session_id)
        if entry is None:
            return {"ok": True}
        _validate_token(entry, picker_token)
        entry.picker_token = None
        entry.picker_mode = None
    session_svc.touch_activity(session_id)
    return {"ok": True}


def _page_for_picker(entry: session_svc._LiveEntry, picker_token: str) -> Page:
    _validate_token(entry, picker_token)
    closed = entry.page.is_closed() if callable(getattr(entry.page, "is_closed", None)) else entry.page.is_closed
    if closed:
        raise PickerError("session page is closed")
    return entry.page


async def navigate_picker(
    session_id: str,
    db: Session,
    *,
    picker_token: str,
    url: str,
) -> dict[str, Any]:
    entry = _require_live_entry(session_id)
    page = _page_for_picker(entry, picker_token)
    await page.goto(url, wait_until="domcontentloaded")
    session_svc.touch_activity(session_id)
    try:
        title = await page.title()
    except Exception:
        title = ""
    return {"url": page.url, "title": title}


async def screenshot_picker(
    session_id: str,
    db: Session,
    *,
    picker_token: str,
) -> tuple[bytes, dict[str, Any]]:
    entry = _require_live_entry(session_id)
    page = _page_for_picker(entry, picker_token)
    viewport = page.viewport_size or {"width": 1280, "height": 720}
    data = await page.screenshot(type="jpeg", quality=80, full_page=False)
    session_svc.touch_activity(session_id)
    meta = {
        "width": viewport.get("width", 1280),
        "height": viewport.get("height", 720),
        "deviceScaleFactor": 1,
    }
    return data, meta


async def pick_element(
    session_id: str,
    db: Session,
    *,
    picker_token: str,
    x: float,
    y: float,
) -> dict[str, Any]:
    entry = _require_live_entry(session_id)
    page = _page_for_picker(entry, picker_token)
    result = await resolve_element_at_point(page, x, y)
    session_svc.touch_activity(session_id)
    return result


async def test_selector(
    session_id: str,
    db: Session,
    *,
    picker_token: str,
    selector: str,
) -> dict[str, Any]:
    entry = _require_live_entry(session_id)
    page = _page_for_picker(entry, picker_token)
    result = await test_selector_on_page(page, selector)
    session_svc.touch_activity(session_id)
    return result
