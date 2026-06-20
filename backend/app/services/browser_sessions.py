"""Live browser session manager: in-memory contexts with 24h TTL and idle eviction."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from playwright.async_api import BrowserContext, Page
from sqlmodel import Session, select

from app.db.models import BrowserProfile, BrowserSession
from app.db.session import engine
from app.settings import settings


logger = logging.getLogger(__name__)

SESSION_TTL = timedelta(hours=24)
MEMORY_LIMIT = 20
EXTRACTED_SUMMARY_LIMIT = 10


class MaxLiveSessionsError(Exception):
    """Raised when creating a session would exceed ``MAX_LIVE_SESSIONS``."""


class SessionNotAvailableError(Exception):
    """Raised when a session is missing, expired, or not live in memory."""


@dataclass
class _LiveEntry:
    context: BrowserContext
    page: Page
    profile_id: Optional[str]
    attached_run_id: Optional[str] = None
    picker_token: Optional[str] = None
    picker_mode: Optional[str] = None


_live: dict[str, _LiveEntry] = {}
_lock = asyncio.Lock()
_reaper_task: Optional[asyncio.Task] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def live_count() -> int:
    return len(_live)


def is_active_in_process(session_id: str) -> bool:
    return session_id in _live


def stats() -> dict[str, Any]:
    return {
        "live": len(_live),
        "capacity": settings.max_live_sessions,
        "available": max(0, settings.max_live_sessions - len(_live)),
    }


def reset_for_tests() -> None:
    """Clear in-memory session tracking (tests only)."""
    _live.clear()


async def _create_context(
    session_id: str,
    profile_id: Optional[str],
    *,
    provider_config: Optional[Any] = None,
) -> _LiveEntry:
    from app.services import browser_pool
    from app.services.browser_providers import BrowserProviderConfig

    cfg = provider_config
    if cfg is not None and not isinstance(cfg, BrowserProviderConfig):
        if isinstance(cfg, dict):
            cfg = BrowserProviderConfig(
                provider_id=str(cfg.get("provider_id") or "local_playwright"),
                config=cfg.get("config") or cfg,
            )
    rb = await browser_pool.create_context_entry(
        session_id, profile_id, provider_config=cfg
    )
    return _LiveEntry(
        context=rb.context,
        page=rb.page,
        profile_id=rb.profile_id,
    )


def _persist_row(row: BrowserSession, session: Session) -> BrowserSession:
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _get_row(session_id: str, db: Session) -> Optional[BrowserSession]:
    return db.get(BrowserSession, session_id)


def _validate_profile(profile_id: Optional[str], db: Session) -> None:
    if profile_id is None:
        return
    profile = db.get(BrowserProfile, profile_id)
    if profile is None:
        raise ValueError(f"browser profile {profile_id!r} not found")


async def create_session(
    db: Session,
    *,
    profile_id: Optional[str] = None,
    provider_id: Optional[str] = None,
    provider_config: Optional[dict[str, Any]] = None,
) -> BrowserSession:
    """Create a live session row and hold its Playwright context in memory."""
    from app.services.browser_providers import (
        BrowserProviderConfig,
        get_provider,
        require_capability,
        sanitize_provider_metadata,
    )

    _validate_profile(profile_id, db)
    resolved_provider_id = (provider_id or "local_playwright").strip().lower()
    raw_config = dict(provider_config or {})
    if profile_id and resolved_provider_id != "local_playwright":
        provider = get_provider(
            BrowserProviderConfig(provider_id=resolved_provider_id, config=raw_config)
        )
        require_capability(provider, "persistent_context")
    safe_metadata = sanitize_provider_metadata(raw_config)
    provider_cfg = BrowserProviderConfig(
        provider_id=resolved_provider_id,
        config=raw_config,
    )
    async with _lock:
        if len(_live) >= settings.max_live_sessions:
            raise MaxLiveSessionsError(
                f"max live sessions reached ({settings.max_live_sessions})"
            )
        now = _utcnow()
        row = BrowserSession(
            profile_id=profile_id,
            status="live",
            started_at=now,
            expires_at=now + SESSION_TTL,
            last_activity_at=now,
            provider_id=resolved_provider_id,
            provider_metadata_json=json.dumps(safe_metadata, ensure_ascii=False),
        )
        row = _persist_row(row, db)
        try:
            entry = await _create_context(
                row.id, profile_id, provider_config=provider_cfg
            )
        except Exception:
            row.status = "closed"
            db.add(row)
            db.commit()
            raise
        _live[row.id] = entry
        return row


def list_sessions(db: Session) -> list[BrowserSession]:
    return list(
        db.exec(
            select(BrowserSession).order_by(BrowserSession.started_at.desc())  # type: ignore[attr-defined]
        ).all()
    )


def get_session_row(session_id: str, db: Session) -> Optional[BrowserSession]:
    return _get_row(session_id, db)


def _read_memory(row: BrowserSession) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(row.memory_json or "[]")
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def list_memory_entries(db: Session, session_id: str) -> list[dict[str, Any]]:
    row = _get_row(session_id, db)
    if row is None:
        raise SessionNotAvailableError(f"browser session {session_id!r} not found")
    return _read_memory(row)


def append_memory_entry(
    db: Session,
    session_id: str,
    *,
    objective: str,
    success: bool,
    summary: str,
    final_url: Optional[str],
    extracted_items: list[Any],
) -> dict[str, Any]:
    row = _get_row(session_id, db)
    if row is None:
        raise SessionNotAvailableError(f"browser session {session_id!r} not found")
    entries = _read_memory(row)
    entry = {
        "objective": objective,
        "success": bool(success),
        "summary": summary,
        "final_url": final_url,
        "extracted_summary": extracted_items[:EXTRACTED_SUMMARY_LIMIT],
        "created_at": _utcnow().isoformat(),
    }
    entries.append(entry)
    entries = entries[-MEMORY_LIMIT:]
    row.memory_json = json.dumps(entries, ensure_ascii=False, default=str)
    row.last_activity_at = _utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return entry


def clear_memory_entries(db: Session, session_id: str) -> list[dict[str, Any]]:
    row = _get_row(session_id, db)
    if row is None:
        raise SessionNotAvailableError(f"browser session {session_id!r} not found")
    row.memory_json = "[]"
    row.last_activity_at = _utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return []


async def keep_alive(session_id: str, db: Session) -> BrowserSession:
    """Refresh ``last_activity_at`` for an in-memory live session."""
    row = _get_row(session_id, db)
    if row is None:
        raise SessionNotAvailableError(f"browser session {session_id!r} not found")
    if row.status != "live" or session_id not in _live:
        raise SessionNotAvailableError(f"browser session {session_id!r} is not live")
    row.last_activity_at = _utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def touch_activity(session_id: str) -> None:
    """Update ``last_activity_at`` after a run uses the session."""
    with Session(engine) as db:
        row = _get_row(session_id, db)
        if row is None:
            return
        row.last_activity_at = _utcnow()
        db.add(row)
        db.commit()


async def acquire_for_run(
    session_id: str,
    run_id: str,
) -> tuple[BrowserContext, Page, Optional[str]]:
    """Attach a run to an existing live session context."""
    async with _lock:
        row: Optional[BrowserSession] = None
        with Session(engine) as db:
            row = _get_row(session_id, db)
            if row is None:
                raise SessionNotAvailableError(
                    f"browser session {session_id!r} not found"
                )
            if row.status != "live":
                raise SessionNotAvailableError(
                    f"browser session {session_id!r} is {row.status}"
                )
            now = _utcnow()
            if _ensure_aware(row.expires_at) <= now:
                raise SessionNotAvailableError(
                    f"browser session {session_id!r} has expired"
                )
        entry = _live.get(session_id)
        if entry is None:
            raise SessionNotAvailableError(
                f"browser session {session_id!r} is not active in this process"
            )
        if entry.picker_token:
            raise SessionNotAvailableError(
                f"browser session {session_id!r} has active element picker"
            )
        if entry.attached_run_id and entry.attached_run_id != run_id:
            raise SessionNotAvailableError(
                f"browser session {session_id!r} is already in use"
            )
        entry.attached_run_id = run_id
    touch_activity(session_id)
    return entry.context, entry.page, entry.profile_id


async def release(session_id: str, *, keep_alive: bool = False) -> None:
    """Release a session after a run finishes."""
    async with _lock:
        entry = _live.get(session_id)
        if entry is not None:
            entry.attached_run_id = None
        if keep_alive:
            touch_activity(session_id)
            return
        await _close_session_locked(session_id, status="closed")


async def close_session(session_id: str, *, status: str = "closed") -> None:
    """Explicitly close a live session."""
    async with _lock:
        await _close_session_locked(session_id, status=status)


async def _close_session_locked(session_id: str, *, status: str) -> None:
    entry = _live.pop(session_id, None)
    if entry is not None:
        from app.services import browser_pool

        await browser_pool.close_context_entry(entry.context, entry.page)
    with Session(engine) as db:
        row = _get_row(session_id, db)
        if row is None:
            return
        if row.status == "live":
            row.status = status
            db.add(row)
            db.commit()


async def _reap_once() -> int:
    now = _utcnow()
    idle_cutoff = now - timedelta(minutes=settings.session_idle_minutes)
    reaped = 0
    to_close: list[tuple[str, str]] = []

    with Session(engine) as db:
        rows = db.exec(
            select(BrowserSession).where(BrowserSession.status == "live")
        ).all()
        for row in rows:
            expires_at = _ensure_aware(row.expires_at)
            last_activity = _ensure_aware(row.last_activity_at)
            if expires_at <= now:
                to_close.append((row.id, "expired"))
            elif last_activity <= idle_cutoff and row.id in _live:
                entry = _live.get(row.id)
                if entry is None or entry.attached_run_id is None:
                    to_close.append((row.id, "closed"))

    for session_id, status in to_close:
        await close_session(session_id, status=status)
        reaped += 1
    return reaped


async def _reaper_loop() -> None:
    while True:
        try:
            await asyncio.sleep(60)
            count = await _reap_once()
            if count:
                logger.info("browser session reaper closed %s session(s)", count)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("browser session reaper tick failed")


def expire_all_live_on_startup() -> int:
    """Mark all previously-live sessions expired after backend restart."""
    expired = 0
    with Session(engine) as session:
        rows = session.exec(
            select(BrowserSession).where(BrowserSession.status == "live")
        ).all()
        for row in rows:
            row.status = "expired"
            session.add(row)
            expired += 1
        if expired:
            session.commit()
    _live.clear()
    if expired:
        logger.warning(
            "marked %s live browser session(s) expired after restart", expired
        )
    return expired


def start_reaper() -> None:
    global _reaper_task
    if _reaper_task is not None and not _reaper_task.done():
        return
    _reaper_task = asyncio.create_task(_reaper_loop())


async def shutdown() -> None:
    global _reaper_task
    if _reaper_task is not None:
        _reaper_task.cancel()
        try:
            await _reaper_task
        except asyncio.CancelledError:
            pass
        _reaper_task = None
    async with _lock:
        session_ids = list(_live.keys())
    for session_id in session_ids:
        await close_session(session_id, status="closed")


__all__ = [
    "MaxLiveSessionsError",
    "SessionNotAvailableError",
    "acquire_for_run",
    "close_session",
    "create_session",
    "expire_all_live_on_startup",
    "get_session_row",
    "is_active_in_process",
    "keep_alive",
    "list_sessions",
    "live_count",
    "release",
    "reset_for_tests",
    "shutdown",
    "start_reaper",
    "stats",
    "touch_activity",
]
