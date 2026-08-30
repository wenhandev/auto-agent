"""Executor desktop_* node dispatch with FakeBackend."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from app.executor import _run_node
from app.schemas import Node
from app.services.desktop_computer_use.app_lock import reset_app_locks_for_tests
from app.services.desktop_computer_use.auth import reset_auth_store_for_tests
from app.services.desktop_computer_use.factory import set_desktop_backend_for_tests
from app.services.desktop_computer_use.fake import FakeDesktopComputerUseBackend
from app.services.desktop_computer_use.session import set_session_checker_for_tests


@pytest.fixture(autouse=True)
def _desktop_test_env():
    reset_app_locks_for_tests()
    set_session_checker_for_tests(lambda: None)
    yield
    reset_app_locks_for_tests()
    set_session_checker_for_tests(None)
    set_desktop_backend_for_tests(None)


@pytest.fixture
def backend(tmp_path: Path) -> FakeDesktopComputerUseBackend:
    store = reset_auth_store_for_tests(tmp_path / "auth.json")
    store.allow_always("com.apple.TextEdit")
    fake = FakeDesktopComputerUseBackend(auth=store)
    set_desktop_backend_for_tests(fake)
    yield fake
    if (tmp_path / "auth.json").exists():
        (tmp_path / "auth.json").unlink()


@pytest.mark.asyncio
async def test_desktop_act_emits_desktop_step(
    backend: FakeDesktopComputerUseBackend,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []

    async def emit(event_type: str, **payload: Any) -> None:
        events.append((event_type, payload))

    node = Node(
        id="d1",
        type="desktop_act",
        label="type",
        params={"app": "TextEdit", "instruction": "type hello into field"},
    )
    result = await _run_node(node, emit)
    assert result["completed"] is True
    assert any(et == "desktop_step" for et, _ in events)
    step = next(p for et, p in events if et == "desktop_step")
    assert step.get("app")
    assert "screenshot_ref" in step


@pytest.mark.asyncio
async def test_desktop_open(backend: FakeDesktopComputerUseBackend) -> None:
    async def emit(event_type: str, **payload: Any) -> None:
        await asyncio.sleep(0)

    node = Node(
        id="d0",
        type="desktop_open",
        label="open",
        params={"app": "com.apple.TextEdit"},
    )
    result = await _run_node(node, emit)
    assert result["app_id"] == "com.apple.TextEdit"
