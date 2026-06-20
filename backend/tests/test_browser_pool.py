"""Tests for the bounded browser context pool (mocked Playwright)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.services import browser_pool
from app.settings import settings


class _FakePage:
    is_closed = False

    def __init__(self, context: object) -> None:
        self.context = context


class _FakeContext:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    async def close(self) -> None:
        pass

    async def new_page(self) -> _FakePage:
        return _FakePage(self)


class _FakeBrowser:
    def is_connected(self) -> bool:
        return True

    async def new_context(self, **kwargs) -> _FakeContext:
        return _FakeContext(**kwargs)

    async def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _reset_pool(monkeypatch: pytest.MonkeyPatch):
    browser_pool.reset_for_tests()
    monkeypatch.setattr(settings, "max_concurrent_browser_runs", 3)
    monkeypatch.setattr(settings, "max_parked_contexts", 2)
    fake = _FakeBrowser()
    monkeypatch.setattr(browser_pool, "_browser", fake)
    monkeypatch.setattr(browser_pool, "_playwright", MagicMock())
    yield
    browser_pool.reset_for_tests()


@pytest.mark.asyncio
async def test_acquire_release_isolates_runs() -> None:
    await browser_pool.acquire("run-a")
    await browser_pool.acquire("run-b")
    assert browser_pool.get_page("run-a") is not browser_pool.get_page("run-b")
    assert browser_pool.stats()["active"] == 2
    await browser_pool.release("run-a")
    assert browser_pool.get_page("run-a") is None
    assert browser_pool.get_page("run-b") is not None
    await browser_pool.release("run-b")
    assert browser_pool.stats()["active"] == 0


@pytest.mark.asyncio
async def test_pool_capacity_raises() -> None:
    for i in range(3):
        await browser_pool.acquire(f"run-{i}")
    with pytest.raises(RuntimeError, match="exhausted"):
        await browser_pool.acquire("run-overflow")
    events = browser_pool.pop_saturation_events()
    assert events
    assert events[-1]["event"] == "browser_pool_saturated"


@pytest.mark.asyncio
async def test_park_frees_active_slot() -> None:
    await browser_pool.acquire("run-1")
    assert browser_pool.stats()["active"] == 1
    ok = await browser_pool.park("run-1")
    assert ok is True
    assert browser_pool.stats()["active"] == 0
    assert browser_pool.stats()["parked"] == 1
    assert browser_pool.get_page("run-1") is not None
    await browser_pool.acquire("run-2")
    assert browser_pool.stats()["active"] == 1


@pytest.mark.asyncio
async def test_park_cap_rejects() -> None:
    for rid in ("p1", "p2"):
        await browser_pool.acquire(rid)
        await browser_pool.park(rid)
    await browser_pool.acquire("run-active")
    ok = await browser_pool.park("run-active")
    assert ok is False
    assert browser_pool.stats()["active"] == 1


@pytest.mark.asyncio
async def test_unpark_requires_slot() -> None:
    await browser_pool.acquire("run-1")
    await browser_pool.park("run-1")
    for i in range(3):
        await browser_pool.acquire(f"fill-{i}")
    with pytest.raises(RuntimeError, match="exhausted"):
        await browser_pool.unpark("run-1")
