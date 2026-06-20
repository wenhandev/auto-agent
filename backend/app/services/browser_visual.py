"""Headed-browser visual capture policy.

Playwright ``page.screenshot()`` and CDP screencast visibly flash headed
Chromium windows. Optional captures (extract vision, self-heal vision, live
stream, run artifacts) should be skipped unless headless.
"""

from __future__ import annotations

from app.settings import settings


def skip_optional_page_screenshots() -> bool:
    """True when optional screenshots should not run (headed demo windows)."""
    if settings.browser_headless:
        return False
    return bool(settings.browser_skip_headed_screenshots)


__all__ = ["skip_optional_page_screenshots"]
