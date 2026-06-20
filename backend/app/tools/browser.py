from __future__ import annotations

import asyncio
from typing import Any, Optional

from playwright.async_api import BrowserContext, Page

from app.services import artifact_context
from app.services import browser_pool
from app.settings import settings

# Legacy module-level handles for single-run / test monkeypatch compatibility.
_lock = asyncio.Lock()
_context: Optional[BrowserContext] = None
_page: Optional[Page] = None
_trace_run_id: Optional[str] = None
_active_profile_id: Optional[str] = None
_legacy_run_id: Optional[str] = None


def _current_run_id(explicit: Optional[str] = None) -> Optional[str]:
    if explicit is not None:
        return explicit
    return artifact_context.get_run_id() or _legacy_run_id


async def begin_run(
    profile_id: Optional[str] = None,
    *,
    run_id: Optional[str] = None,
    browser_session_id: Optional[str] = None,
) -> None:
    """Open a fresh browser context for a run, optionally seeded from a profile."""
    global _active_profile_id, _page, _context, _legacy_run_id
    rid = _current_run_id(run_id)
    if browser_session_id and rid is not None:
        from app.services import browser_sessions as session_svc

        ctx, page, session_profile_id = await session_svc.acquire_for_run(
            browser_session_id, rid
        )
        effective_profile = profile_id or session_profile_id
        async with _lock:
            _active_profile_id = effective_profile
            await browser_pool.attach_run(rid, ctx, page, effective_profile)
        return
    if rid is None:
        async with _lock:
            await _close_legacy_page_and_context()
            _legacy_run_id = "__legacy__"
            _active_profile_id = profile_id
            await browser_pool.acquire("__legacy__", profile_id)
            ctx = browser_pool.get_context("__legacy__")
            page = browser_pool.get_page("__legacy__")
            _context = ctx
            _page = page
        return

    async with _lock:
        _active_profile_id = profile_id
        await browser_pool.acquire(rid, profile_id)


async def end_run(
    *,
    run_id: Optional[str] = None,
    browser_session_id: Optional[str] = None,
) -> None:
    """Persist profile storage_state when configured, then tear down the context."""
    global _active_profile_id, _context, _page, _legacy_run_id
    rid = _current_run_id(run_id)
    if rid is None:
        return
    async with _lock:
        if browser_session_id:
            from app.services import browser_sessions as session_svc

            await browser_pool.detach_run(rid)
            await session_svc.release(browser_session_id, keep_alive=True)
            if artifact_context.get_run_id() == rid:
                _active_profile_id = None
            return
        if rid == "__legacy__":
            await browser_pool.release("__legacy__")
            _context = None
            _page = None
            _legacy_run_id = None
            _active_profile_id = None
            return
        await browser_pool.release(rid)
        if artifact_context.get_run_id() == rid:
            _active_profile_id = None


def get_active_profile_id() -> Optional[str]:
    rid = _current_run_id()
    if rid:
        pooled = browser_pool.get_profile_id(rid)
        if pooled is not None:
            return pooled
    return _active_profile_id


def get_active_context() -> Optional[BrowserContext]:
    rid = _current_run_id()
    if rid:
        ctx = browser_pool.get_context(rid)
        if ctx is not None:
            return ctx
    return _context


def get_active_page(run_id: Optional[str] = None) -> Optional[Page]:
    rid = _current_run_id(run_id)
    if rid:
        page = browser_pool.get_page(rid)
        if page is not None:
            return page
    if _page is not None and not _page_is_closed(_page):
        return _page
    return None


def _page_is_closed(page: Page) -> bool:
    is_closed = getattr(page, "is_closed", None)
    if callable(is_closed):
        return bool(is_closed())
    return bool(is_closed)


async def get_page() -> Page:
    async with _lock:
        page = get_active_page()
        if page is not None:
            return page
    # begin_run acquires _lock internally — must not call it while holding _lock
    await begin_run(None)
    async with _lock:
        page = get_active_page()
        assert page is not None
        return page


async def park_for_approval(*, run_id: Optional[str] = None) -> bool:
    rid = _current_run_id(run_id)
    if rid is None or rid == "__legacy__":
        return True
    return await browser_pool.park(rid)


async def unpark_after_approval(*, run_id: Optional[str] = None) -> None:
    rid = _current_run_id(run_id)
    if rid is None or rid == "__legacy__":
        return
    await browser_pool.unpark(rid)


async def _close_legacy_page_and_context() -> None:
    global _context, _page
    try:
        if _page is not None and not _page_is_closed(_page):
            await _page.close()
    except Exception:
        pass
    _page = None
    try:
        if _context is not None:
            await _context.close()
    except Exception:
        pass
    _context = None


async def start_run_trace(run_id: str) -> None:
    """Start Playwright tracing for a run when enabled."""
    global _trace_run_id
    if not settings.record_playwright_trace:
        return
    try:
        page = await get_page()
        await page.context.tracing.start(screenshots=True, snapshots=True)
        _trace_run_id = run_id
    except Exception:
        _trace_run_id = None


async def stop_run_trace(run_id: str) -> None:
    """Stop tracing and persist as a trace artifact."""
    global _trace_run_id
    if _trace_run_id != run_id:
        return
    _trace_run_id = None
    try:
        import tempfile
        from pathlib import Path

        from app.services import artifacts as artifact_svc

        page = await get_page()
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = tmp.name
        await page.context.tracing.stop(path=tmp_path)
        data = Path(tmp_path).read_bytes()
        Path(tmp_path).unlink(missing_ok=True)
        artifact_svc.store_bytes(run_id, "trace", data, content_type="application/zip")
    except Exception:
        pass


async def shutdown() -> None:
    global _legacy_run_id, _active_profile_id
    async with _lock:
        await _close_legacy_page_and_context()
        _legacy_run_id = None
        _active_profile_id = None
    from app.services import browser_sessions as session_svc

    await session_svc.shutdown()
    await browser_pool.shutdown()


def pool_stats() -> dict[str, Any]:
    return browser_pool.stats()
