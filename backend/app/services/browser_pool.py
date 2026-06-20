"""Bounded pool of isolated Playwright browser contexts over one browser process."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from app.settings import settings


logger = logging.getLogger(__name__)


@dataclass
class _RunBrowser:
    run_id: str
    context: BrowserContext
    page: Page
    profile_id: Optional[str] = None
    parked: bool = False


_playwright: Optional[Playwright] = None
_browser: Optional[Browser] = None
_active: dict[str, _RunBrowser] = {}
_parked: dict[str, _RunBrowser] = {}
_lock = asyncio.Lock()
_saturation_events: list[dict[str, Any]] = []


async def _ensure_browser() -> Browser:
    from app.settings import settings

    if settings.execution_backend == "control_plane_only":
        raise RuntimeError(
            "Playwright is disabled (EXECUTION_BACKEND=control_plane_only); "
            "use worker-mode runs or set EXECUTION_BACKEND=full"
        )
    global _playwright, _browser
    if _playwright is None:
        _playwright = await async_playwright().start()
    if _browser is None or not _browser.is_connected():
        launch_kwargs: dict[str, Any] = {"headless": settings.browser_headless}
        if not settings.browser_headless:
            w = settings.browser_viewport_width
            h = settings.browser_viewport_height
            launch_kwargs["args"] = [f"--window-size={w},{h}"]
        _browser = await _playwright.chromium.launch(**launch_kwargs)
    return _browser


async def _create_context(
    run_id: str,
    profile_id: Optional[str],
    *,
    provider_config: Optional[Any] = None,
) -> _RunBrowser:
    from app.services.browser_providers import BrowserProviderConfig, create_browser_connection

    cfg = provider_config
    if cfg is not None and not isinstance(cfg, BrowserProviderConfig):
        cfg = BrowserProviderConfig(**cfg) if isinstance(cfg, dict) else None
    conn = await create_browser_connection(run_id, profile_id=profile_id, config=cfg)
    return _RunBrowser(
        run_id=run_id,
        context=conn.context,
        page=conn.page,
        profile_id=profile_id or conn.profile_id,
    )


async def create_context_entry(
    run_id: str,
    profile_id: Optional[str],
    *,
    provider_config: Optional[Any] = None,
) -> _RunBrowser:
    """Create an isolated context (used by live sessions and the run pool)."""
    return await _create_context(run_id, profile_id, provider_config=provider_config)


async def close_context_entry(context: BrowserContext, page: Page) -> None:
    """Close a context/page pair without pool bookkeeping."""
    rb = _RunBrowser(run_id="", context=context, page=page)
    await _close_run_browser(rb)


async def _close_run_browser(rb: _RunBrowser) -> None:
    try:
        if not _page_is_closed(rb.page):
            await rb.page.close()
    except Exception:
        pass
    try:
        await rb.context.close()
    except Exception:
        pass


def _record_saturation(reason: str) -> None:
    event = {
        "event": "browser_pool_saturated",
        "active": len(_active),
        "parked": len(_parked),
        "capacity": settings.max_concurrent_browser_runs,
        "reason": reason,
    }
    _saturation_events.append(event)
    if len(_saturation_events) > 100:
        del _saturation_events[:50]
    logger.info("browser pool saturated: %s", event)


def stats() -> dict[str, Any]:
    cap = settings.max_concurrent_browser_runs
    active = len(_active)
    return {
        "active": active,
        "parked": len(_parked),
        "capacity": cap,
        "parked_capacity": settings.max_parked_contexts,
        "available": max(0, cap - active),
        "saturated": active >= cap,
    }


def pop_saturation_events() -> list[dict[str, Any]]:
    events = list(_saturation_events)
    _saturation_events.clear()
    return events


def has_active_slot() -> bool:
    return len(_active) < settings.max_concurrent_browser_runs


async def acquire(run_id: str, profile_id: Optional[str] = None) -> None:
    """Borrow a pool slot and create (or reuse) an isolated context for a run."""
    async with _lock:
        if run_id in _active:
            return
        parked = _parked.pop(run_id, None)
        if parked is not None:
            parked.parked = False
            _active[run_id] = parked
            return
        if len(_active) >= settings.max_concurrent_browser_runs:
            _record_saturation("acquire")
            raise RuntimeError("browser pool exhausted")
        rb = await _create_context(run_id, profile_id)
        _active[run_id] = rb


async def release(run_id: str) -> None:
    """Close and remove a run's context from the pool."""
    from app.services.browser_capture import clear_run_capture, finalize_har_after_context_close

    async with _lock:
        rb = _active.pop(run_id, None)
        if rb is None:
            rb = _parked.pop(run_id, None)
        if rb is None:
            clear_run_capture(run_id)
            return
        profile_id = rb.profile_id
        context = rb.context
    if profile_id and context is not None:
        from app.services.browser_profiles import save_from_context

        try:
            await save_from_context(profile_id, context)
        except Exception:
            pass
    if rb is not None:
        await _close_run_browser(rb)
        await finalize_har_after_context_close(run_id)
    clear_run_capture(run_id)


async def attach_run(
    run_id: str,
    context: BrowserContext,
    page: Page,
    profile_id: Optional[str] = None,
) -> None:
    """Attach a run to an existing context (live session reuse)."""
    from app.services.browser_capture import attach_download_listener

    async with _lock:
        if run_id in _active:
            return
        if len(_active) >= settings.max_concurrent_browser_runs:
            _record_saturation("attach_run")
            raise RuntimeError("browser pool exhausted")
        _active[run_id] = _RunBrowser(
            run_id=run_id,
            context=context,
            page=page,
            profile_id=profile_id,
        )
    attach_download_listener(run_id, page)


async def detach_run(run_id: str) -> None:
    """Remove a run from the pool without closing its context."""
    from app.services.browser_capture import clear_run_capture

    async with _lock:
        _active.pop(run_id, None)
        _parked.pop(run_id, None)
    clear_run_capture(run_id)


async def park(run_id: str) -> bool:
    """Park a context (keeps it alive) and free the active pool slot.

    Returns False when ``MAX_PARKED_CONTEXTS`` would be exceeded (slot held).
    """
    async with _lock:
        rb = _active.get(run_id)
        if rb is None:
            return True
        if len(_parked) >= settings.max_parked_contexts:
            logger.warning(
                "park rejected run=%s parked=%s cap=%s",
                run_id,
                len(_parked),
                settings.max_parked_contexts,
            )
            return False
        del _active[run_id]
        rb.parked = True
        _parked[run_id] = rb
        return True


async def unpark(run_id: str) -> None:
    """Move a parked context back into the active pool (must have a free slot)."""
    async with _lock:
        rb = _parked.get(run_id)
        if rb is None:
            if run_id in _active:
                return
            return
        if len(_active) >= settings.max_concurrent_browser_runs:
            _record_saturation("unpark")
            raise RuntimeError("browser pool exhausted")
        del _parked[run_id]
        rb.parked = False
        _active[run_id] = rb


def _page_is_closed(page: Page) -> bool:
    is_closed = getattr(page, "is_closed", None)
    if callable(is_closed):
        return bool(is_closed())
    return bool(is_closed)


def get_page(run_id: Optional[str]) -> Optional[Page]:
    if not run_id:
        return None
    rb = _active.get(run_id) or _parked.get(run_id)
    if rb is None:
        return None
    if _page_is_closed(rb.page):
        return None
    return rb.page


def get_context(run_id: Optional[str]) -> Optional[BrowserContext]:
    if not run_id:
        return None
    rb = _active.get(run_id) or _parked.get(run_id)
    return rb.context if rb else None


def get_profile_id(run_id: Optional[str]) -> Optional[str]:
    if not run_id:
        return None
    rb = _active.get(run_id) or _parked.get(run_id)
    return rb.profile_id if rb else None


async def shutdown() -> None:
    global _playwright, _browser
    async with _lock:
        for rb in list(_active.values()) + list(_parked.values()):
            await _close_run_browser(rb)
        _active.clear()
        _parked.clear()
        browser = _browser
        pw = _playwright
        _browser = None
        _playwright = None
    try:
        if browser is not None and browser.is_connected():
            await browser.close()
    except Exception:
        pass
    try:
        if pw is not None:
            await pw.stop()
    except Exception:
        pass


def reset_for_tests() -> None:
    """Clear in-memory pool tracking without closing Playwright (tests only)."""
    _active.clear()
    _parked.clear()
    _saturation_events.clear()


__all__ = [
    "acquire",
    "attach_run",
    "close_context_entry",
    "create_context_entry",
    "detach_run",
    "get_context",
    "get_page",
    "get_profile_id",
    "has_active_slot",
    "park",
    "pop_saturation_events",
    "release",
    "reset_for_tests",
    "shutdown",
    "stats",
    "unpark",
]
