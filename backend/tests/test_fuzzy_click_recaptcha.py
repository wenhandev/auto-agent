"""Tests for reCAPTCHA iframe checkbox click helper."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.agents.fuzzy import _click_recaptcha_in_page


class _AnchorLocator:
    def __init__(self, *, count: int = 1, visible: bool = True) -> None:
        self._count = count
        self._visible = visible
        self.first = self
        self.click = AsyncMock()
        self.is_visible = AsyncMock(return_value=visible)

    async def count(self) -> int:
        return self._count


class _AnchorFrame:
    def __init__(self, *, token_present: bool = True) -> None:
        self.url = "https://www.google.com/recaptcha/api2/anchor?k=test"
        self._token_present = token_present
        self._anchor = _AnchorLocator()
        self._checked = _AnchorLocator(count=1 if token_present else 0, visible=token_present)
        self.wait_for_selector = AsyncMock()
        self.click = AsyncMock()
        self.locator = MagicMock(side_effect=self._locator)

    def _locator(self, selector: str) -> _AnchorLocator:
        if "checked" in selector or "aria-checked" in selector:
            return self._checked
        return self._anchor


class _FrameLocator:
    def __init__(self, anchor: _AnchorLocator) -> None:
        self._anchor = anchor
        self.first = self

    def locator(self, _selector: str) -> _AnchorLocator:
        return self._anchor


class _Page:
    def __init__(
        self,
        *,
        token_present: bool = True,
        anchor_count: int = 1,
        anchor_frame: _AnchorFrame | None = None,
    ) -> None:
        self.url = "http://127.0.0.1:8001/static/recaptcha-form.html"
        self.title = AsyncMock(return_value="Secure Registration")
        self._token_present = token_present
        self._anchor = _AnchorLocator(count=anchor_count)
        self.frames = [anchor_frame] if anchor_frame else []
        self.wait_for_selector = AsyncMock()

    async def evaluate(self, script: str) -> Any:
        if "g-recaptcha-response" in script:
            return self._token_present
        return None

    def frame_locator(self, _selector: str) -> _FrameLocator:
        return _FrameLocator(self._anchor)


@pytest.mark.asyncio
async def test_click_recaptcha_in_page_success() -> None:
    page = _Page(token_present=True, anchor_frame=_AnchorFrame(token_present=True))

    result = await _click_recaptcha_in_page(page)

    assert result["clicked"] is True
    assert result["method"] == "frame_click"
    assert result["token_present"] is True
    page.frames[0].click.assert_awaited()


@pytest.mark.asyncio
async def test_click_recaptcha_in_page_no_iframe() -> None:
    page = _Page(anchor_count=0)

    result = await _click_recaptcha_in_page(page)

    assert "error" in result
    assert "could not find or click reCAPTCHA checkbox" in result["error"]
