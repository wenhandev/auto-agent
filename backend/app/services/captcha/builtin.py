"""Built-in CAPTCHA heuristics before external/manual fallback.

Skyvern Cloud bundles proprietary solvers; locally we try cheap Playwright
heuristics (reCAPTCHA checkbox click, slider puzzle drag) first, then fall
through to external HTTP solver or human-in-the-loop approval.
"""

from __future__ import annotations

import logging
from typing import Any

from playwright.async_api import Page

from app.services.captcha.detection import CaptchaInfo, detect_captcha
from app.services.captcha.solver import CaptchaChallenge, CaptchaSolveResult

logger = logging.getLogger(__name__)

_PUZZLE_THUMB = "#slider-thumb"
_PUZZLE_TRACK = "#captcha-track"


async def _captcha_cleared(page: Page) -> bool:
    info = await detect_captcha(page)
    return not info.present


async def _try_recaptcha_click(page: Page) -> CaptchaSolveResult | None:
    from app.agents.fuzzy import _click_recaptcha_in_page

    result = await _click_recaptcha_in_page(page)
    if result.get("error"):
        logger.debug("builtin recaptcha click failed: %s", result.get("error"))
        return None

    if result.get("token_present"):
        return CaptchaSolveResult(success=True, cost_hint="builtin:recaptcha_token")

    if result.get("checkbox_checked") and await _captcha_cleared(page):
        return CaptchaSolveResult(success=True, cost_hint="builtin:recaptcha_click")

    if result.get("clicked") and await _captcha_cleared(page):
        return CaptchaSolveResult(success=True, cost_hint="builtin:recaptcha_click")

    return None


async def _try_puzzle_drag(page: Page) -> CaptchaSolveResult | None:
    try:
        thumb = page.locator(_PUZZLE_THUMB).first
        track = page.locator(_PUZZLE_TRACK).first
        if await thumb.count() == 0 or await track.count() == 0:
            return None
    except Exception:
        return None

    from app.agents.fuzzy import drag_puzzle_captcha

    result = await drag_puzzle_captcha(
        thumb_selector=_PUZZLE_THUMB,
        track_selector=_PUZZLE_TRACK,
        page=page,
    )
    if result.get("error"):
        logger.debug("builtin puzzle drag failed: %s", result.get("error"))
        return None

    if result.get("verified_badge_visible") or await _captcha_cleared(page):
        return CaptchaSolveResult(success=True, cost_hint="builtin:puzzle_drag")

    return None


async def try_builtin_solve(challenge: CaptchaChallenge) -> CaptchaSolveResult | None:
    """Attempt built-in heuristics; return None to fall through to configured solver."""
    page = challenge.page
    kind = challenge.info.kind

    if kind == "recaptcha":
        solved = await _try_recaptcha_click(page)
        if solved is not None:
            return solved

    if kind in ("unknown", "recaptcha", None):
        solved = await _try_puzzle_drag(page)
        if solved is not None:
            return solved

    return None


__all__ = ["try_builtin_solve"]
