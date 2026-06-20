"""Tests for fuzzy drag_puzzle_captcha helper."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.agents.fuzzy import _detect_puzzle_gap, drag_puzzle_captcha


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

    async def get_attribute(self, name: str) -> str | None:
        return ""


class _Page:
    def __init__(self) -> None:
        self.url = "http://127.0.0.1:8001/static/challenge-form-v2.html"
        self.mouse = MagicMock()
        self.mouse.move = AsyncMock()
        self.mouse.down = AsyncMock()
        self.mouse.up = AsyncMock()
        self.title = AsyncMock(return_value="滑动拼图验证 — Secure Registration")
        self._locators: dict[str, _Locator] = {}
        self._evaluate_result: dict[str, Any] = {
            "gap_x": 180,
            "target_thumb_left": 145.0,
            "max_thumb_left": 280,
        }

    def locator(self, selector: str) -> _Locator:
        return self._locators.get(selector, _Locator(0, None))

    async def evaluate(self, _js: str) -> dict[str, Any]:
        return self._evaluate_result


@pytest.mark.asyncio
async def test_detect_puzzle_gap_returns_target() -> None:
    page = _Page()
    result = await _detect_puzzle_gap(page)
    assert result["gap_x"] == 180
    assert result["target_thumb_left"] == 145.0


@pytest.mark.asyncio
async def test_drag_puzzle_captcha_success() -> None:
    page = _Page()
    page._locators["#slider-thumb"] = _Locator(1, {"x": 10, "y": 200, "width": 36, "height": 36})
    page._locators["#captcha-track"] = _Locator(1, {"x": 10, "y": 200, "width": 320, "height": 42})
    page._locators["#verify-badge.visible, .badge.visible"] = _Locator(
        1, {"x": 0, "y": 0, "width": 10, "height": 10}
    )
    page._locators["#captcha-fail"] = _Locator(1, {"x": 0, "y": 0, "width": 10, "height": 10})

    with patch("app.agents.fuzzy.get_page", AsyncMock(return_value=page)):
        result = await drag_puzzle_captcha(steps=8, jitter=True)

    assert result["dragged"] is True
    assert result["method"] == "puzzle_drag"
    assert result["verified_badge_visible"] is True
    assert result["gap_x"] == 180
    page.mouse.down.assert_awaited_once()
    page.mouse.up.assert_awaited_once()
    assert page.mouse.move.await_count >= 2


@pytest.mark.asyncio
async def test_drag_puzzle_captcha_missing_thumb() -> None:
    page = _Page()
    page._locators["#slider-thumb"] = _Locator(0, None)
    page._locators["#captcha-track"] = _Locator(1, {"x": 10, "y": 200, "width": 320, "height": 42})

    with patch("app.agents.fuzzy.get_page", AsyncMock(return_value=page)):
        result = await drag_puzzle_captcha()

    assert "error" in result
    assert "thumb not found" in result["error"]
