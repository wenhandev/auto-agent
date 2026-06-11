from __future__ import annotations

import asyncio
from typing import Optional

from playwright.async_api import Browser, Page, Playwright, async_playwright

from app.settings import settings


_lock = asyncio.Lock()
_playwright: Optional[Playwright] = None
_browser: Optional[Browser] = None
_page: Optional[Page] = None


async def get_page() -> Page:
    global _playwright, _browser, _page
    async with _lock:
        if _page is not None and not _page.is_closed():
            return _page
        if _playwright is None:
            _playwright = await async_playwright().start()
        if _browser is None or not _browser.is_connected():
            _browser = await _playwright.chromium.launch(headless=settings.browser_headless)
        _page = await _browser.new_page()
        return _page


async def shutdown() -> None:
    global _playwright, _browser, _page
    async with _lock:
        try:
            if _page is not None and not _page.is_closed():
                await _page.close()
        except Exception:
            pass
        _page = None
        try:
            if _browser is not None and _browser.is_connected():
                await _browser.close()
        except Exception:
            pass
        _browser = None
        try:
            if _playwright is not None:
                await _playwright.stop()
        except Exception:
            pass
        _playwright = None
