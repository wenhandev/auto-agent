"""CaptchaSolver strategy interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from playwright.async_api import Page

from app.services.captcha.detection import CaptchaInfo


@dataclass
class CaptchaChallenge:
    page: Page
    info: CaptchaInfo
    screenshot_ref: str
    url: str


@dataclass
class CaptchaSolveResult:
    success: bool
    token: Optional[str] = None
    cost_hint: Optional[str] = None
    error: Optional[str] = None


class CaptchaSolver(ABC):
    @abstractmethod
    async def solve(self, challenge: CaptchaChallenge) -> CaptchaSolveResult:
        ...


def get_solver() -> CaptchaSolver:
    from app.settings import settings

    mode = (settings.captcha_solver or "manual").lower()
    if mode == "external":
        from app.services.captcha.external import ExternalCaptchaSolver

        return ExternalCaptchaSolver()
    from app.services.captcha.manual import ManualCaptchaSolver

    return ManualCaptchaSolver()


__all__ = [
    "CaptchaChallenge",
    "CaptchaSolveResult",
    "CaptchaSolver",
    "get_solver",
]
