"""Tests for fuzzy click_text smart interaction strategies."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.agents.fuzzy import _click_text_smart


class _ChainableLocator:
    def __init__(
        self,
        *,
        count: int = 1,
        visible: bool = True,
        href: str | None = None,
        click_error: Exception | None = None,
    ) -> None:
        self._count = count
        self._visible = visible
        self._href = href
        self._click_error = click_error
        self.click = AsyncMock(side_effect=self._click)
        self.is_visible = AsyncMock(return_value=visible)
        self.get_attribute = AsyncMock(return_value=href)
        self.locator = MagicMock(return_value=self)

    async def count(self) -> int:
        return self._count

    async def _click(self, **kwargs: Any) -> None:
        if self._click_error is not None:
            raise self._click_error
        if kwargs.get("force"):
            return
        if not self._visible:
            raise RuntimeError("element is not visible")


class _Page:
    def __init__(self, locator: _ChainableLocator) -> None:
        self.url = "https://www.apple.com.cn/"
        self._locator = locator
        self.goto = AsyncMock()
        self.title = AsyncMock(return_value="Apple")

    def get_by_text(self, text: str, exact: bool = False) -> Any:
        return MagicMock(first=self._locator)


@pytest.mark.asyncio
async def test_click_text_smart_visible_click() -> None:
    page = _Page(_ChainableLocator(visible=True))
    result = await _click_text_smart(page, "Store")
    assert result["method"] == "visible_click"
    assert result["clicked_text"] == "Store"
    page._locator.click.assert_awaited()


@pytest.mark.asyncio
async def test_click_text_smart_force_click_when_hidden() -> None:
    locator = _ChainableLocator(visible=False)
    page = _Page(locator)
    result = await _click_text_smart(page, "iPhone")
    assert result["method"] == "force_click"
    locator.click.assert_awaited_with(force=True, timeout=2000)


@pytest.mark.asyncio
async def test_click_text_smart_href_fallback() -> None:
    locator = _ChainableLocator(
        visible=False,
        href="/iphone/",
        click_error=RuntimeError("not visible"),
    )
    page = _Page(locator)
    result = await _click_text_smart(page, "iPhone")
    assert result["method"] == "href_navigate"
    assert result["href"] == "https://www.apple.com.cn/iphone/"
    page.goto.assert_awaited_once()


@pytest.mark.asyncio
async def test_click_text_smart_returns_retry_error() -> None:
    locator = _ChainableLocator(visible=False, click_error=RuntimeError("blocked"))
    page = _Page(locator)
    result = await _click_text_smart(page, "iPhone")
    assert "error" in result
    assert "retry_hint" in result
    assert "iPhone" in result["error"]
