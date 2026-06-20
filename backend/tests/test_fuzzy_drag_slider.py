"""Tests for fuzzy drag_slider mouse-drag helper."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.agents.fuzzy import _drag_horizontal


class _Locator:
    def __init__(self, count: int, box: dict[str, float] | None) -> None:
        self._count = count
        self._box = box
        self.first = self

    async def count(self) -> int:
        return self._count

    async def bounding_box(self) -> dict[str, float] | None:
        return self._box

    async def is_visible(self) -> bool:
        return True


class _Page:
    def __init__(self) -> None:
        self.url = "http://127.0.0.1:8001/static/challenge-form.html"
        self.mouse = MagicMock()
        self.mouse.move = AsyncMock()
        self.mouse.down = AsyncMock()
        self.mouse.up = AsyncMock()
        self.title = AsyncMock(return_value="Secure Registration Challenge")
        self._locators: dict[str, _Locator] = {}

    def locator(self, selector: str) -> _Locator:
        return self._locators.get(selector, _Locator(0, None))


@pytest.mark.asyncio
async def test_drag_horizontal_success() -> None:
    page = _Page()
    page._locators["#slider-thumb"] = _Locator(1, {"x": 10, "y": 20, "width": 36, "height": 36})
    page._locators["#slider-track"] = _Locator(1, {"x": 10, "y": 20, "width": 300, "height": 44})
    page._locators["#verify-badge.visible, .badge.visible"] = _Locator(1, {"x": 0, "y": 0, "width": 10, "height": 10})

    result = await _drag_horizontal(
        page,
        thumb_selector="#slider-thumb",
        track_selector="#slider-track",
    )

    assert result["dragged"] is True
    assert result["method"] == "mouse_drag"
    assert result["verified_badge_visible"] is True
    page.mouse.down.assert_awaited_once()
    page.mouse.up.assert_awaited_once()
    assert page.mouse.move.await_count >= 2


@pytest.mark.asyncio
async def test_drag_horizontal_missing_thumb() -> None:
    page = _Page()
    page._locators["#slider-thumb"] = _Locator(0, None)
    page._locators["#slider-track"] = _Locator(1, {"x": 10, "y": 20, "width": 300, "height": 44})

    result = await _drag_horizontal(
        page,
        thumb_selector="#slider-thumb",
        track_selector="#slider-track",
    )

    assert "error" in result
    assert "thumb not found" in result["error"]
    page.mouse.down.assert_not_called()
