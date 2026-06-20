"""CAPTCHA marker detection from page DOM and text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal, Optional

from playwright.async_api import Page

CaptchaKind = Literal["recaptcha", "hcaptcha", "turnstile", "unknown"]


@dataclass(frozen=True)
class CaptchaInfo:
    present: bool
    kind: Optional[CaptchaKind] = None

    def to_dict(self) -> dict[str, Any]:
        return {"present": self.present, "kind": self.kind}


_RECAPTCHA_SELECTORS = (
    "iframe[src*='recaptcha']",
    "iframe[title*='reCAPTCHA' i]",
    ".g-recaptcha",
    "#g-recaptcha",
    "[data-sitekey][class*='recaptcha']",
)

_HCAPTCHA_SELECTORS = (
    "iframe[src*='hcaptcha.com']",
    ".h-captcha",
    "[data-sitekey][class*='h-captcha']",
)

_TURNSTILE_SELECTORS = (
    "iframe[src*='challenges.cloudflare.com']",
    ".cf-turnstile",
    "[class*='turnstile']",
)

_CHALLENGE_TEXT_RE = re.compile(
    r"(verify you are human|complete the captcha|security check|"
    r"prove you(?:'|')?re not a robot|i(?:'|')?m not a robot|"
    r"robot check|human verification)",
    re.IGNORECASE,
)


async def _selector_visible(page: Page, selector: str) -> bool:
    try:
        return await page.locator(selector).first.count() > 0
    except Exception:
        return False


async def _first_kind(page: Page, selectors: tuple[str, ...], kind: CaptchaKind) -> Optional[CaptchaKind]:
    for sel in selectors:
        if await _selector_visible(page, sel):
            return kind
    return None


async def detect_captcha(page: Page, *, page_text: str = "") -> CaptchaInfo:
    """Scan the page for common CAPTCHA widgets and challenge copy."""
    for selectors, kind in (
        (_RECAPTCHA_SELECTORS, "recaptcha"),
        (_HCAPTCHA_SELECTORS, "hcaptcha"),
        (_TURNSTILE_SELECTORS, "turnstile"),
    ):
        found = await _first_kind(page, selectors, kind)
        if found:
            return CaptchaInfo(present=True, kind=found)

    text = page_text
    if not text:
        try:
            text = await page.locator("body").inner_text()
        except Exception:
            text = ""
    if text and _CHALLENGE_TEXT_RE.search(text):
        return CaptchaInfo(present=True, kind="unknown")

    return CaptchaInfo(present=False, kind=None)


async def detect_captcha_lightweight(page: Page) -> CaptchaInfo:
    """Fast marker scan after navigation (no screenshot)."""
    return await detect_captcha(page)


__all__ = ["CaptchaInfo", "CaptchaKind", "detect_captcha", "detect_captcha_lightweight"]
