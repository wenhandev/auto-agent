"""Best-effort anti-bot browser context tweaks and stealth init script."""

from __future__ import annotations

from typing import Any, Optional

from playwright.async_api import BrowserContext

from app.db.models import BrowserProfile
from app.settings import settings


STEALTH_INIT_SCRIPT = """
(() => {
  Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
  window.chrome = window.chrome || { runtime: {} };
})();
"""


def global_fingerprint_options() -> dict[str, Any]:
    """Settings-level fingerprint overrides (applied when set)."""
    opts: dict[str, Any] = {}
    if settings.antibot_user_agent:
        opts["user_agent"] = settings.antibot_user_agent
    if settings.antibot_locale:
        opts["locale"] = settings.antibot_locale
    if settings.antibot_timezone_id:
        opts["timezone_id"] = settings.antibot_timezone_id
    if settings.antibot_viewport_width and settings.antibot_viewport_height:
        opts["viewport"] = {
            "width": int(settings.antibot_viewport_width),
            "height": int(settings.antibot_viewport_height),
        }
    return opts


def profile_fingerprint_options(profile: BrowserProfile) -> dict[str, Any]:
    opts: dict[str, Any] = {}
    if profile.user_agent:
        opts["user_agent"] = profile.user_agent
    if profile.locale:
        opts["locale"] = profile.locale
    if profile.timezone_id:
        opts["timezone_id"] = profile.timezone_id
    from app.services.browser_profiles import parse_viewport

    viewport = parse_viewport(profile)
    if viewport is not None:
        opts["viewport"] = viewport
    return opts


def merge_context_options(*parts: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for part in parts:
        merged.update(part)
    return merged


async def apply_stealth_if_enabled(context: BrowserContext) -> None:
    if settings.antibot_stealth:
        await context.add_init_script(STEALTH_INIT_SCRIPT)


__all__ = [
    "STEALTH_INIT_SCRIPT",
    "apply_stealth_if_enabled",
    "global_fingerprint_options",
    "merge_context_options",
    "profile_fingerprint_options",
]
