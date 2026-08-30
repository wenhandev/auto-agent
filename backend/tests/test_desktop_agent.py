"""DesktopAgent tests against FakeBackend."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.desktop import DesktopAgent
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
async def test_run_act_types_into_textfield(backend: FakeDesktopComputerUseBackend) -> None:
    agent = DesktopAgent(backend=backend)
    steps: list[dict] = []

    async def on_step(step: dict) -> None:
        steps.append(step)

    result = await agent.run_act(
        "TextEdit",
        "type hello world into the text area",
        on_step=on_step,
    )
    assert result["completed"] is True
    assert any(s.get("action") == "type_text" for s in steps)
    state = await backend.get_app_state("TextEdit")
    assert "hello world" in (state.elements[0].value or "")


@pytest.mark.asyncio
async def test_run_navigate_emits_desktop_steps(
    backend: FakeDesktopComputerUseBackend,
) -> None:
    agent = DesktopAgent(backend=backend)
    steps: list[dict] = []

    async def on_step(step: dict) -> None:
        steps.append(step)

    result = await agent.run_navigate(
        "TextEdit",
        "click Save",
        max_steps=3,
        on_step=on_step,
        allow_heuristic_short_circuit=True,
    )
    assert result["completed"] is True
    assert any(s.get("action") == "perceive" for s in steps)
    assert any(s.get("screenshot_ref") for s in steps)


@pytest.mark.asyncio
async def test_run_navigate_heuristic_completes_matching_goal(
    backend: FakeDesktopComputerUseBackend,
) -> None:
    agent = DesktopAgent(backend=backend)
    result = await agent.run_navigate(
        "TextEdit",
        "click Save",
        max_steps=3,
        allow_heuristic_short_circuit=False,
    )
    assert result["completed"] is True
    assert result["steps"] >= 1


@pytest.mark.asyncio
async def test_run_navigate_no_false_success_for_unmatched_goal(
    backend: FakeDesktopComputerUseBackend,
) -> None:
    agent = DesktopAgent(backend=backend)
    result = await agent.run_navigate(
        "TextEdit",
        "open preferences and enable dark mode",
        max_steps=2,
        allow_heuristic_short_circuit=False,
    )
    # Heuristic may click buttons, but goal is not satisfied → budget exhausted.
    assert result["completed"] is False
    assert result["summary"] == "max_steps exceeded"


def test_heuristic_goal_satisfied_type_and_click() -> None:
    from app.agents.desktop import heuristic_goal_satisfied
    from app.services.desktop_computer_use.protocol import (
        DesktopAppInfo,
        DesktopAppState,
        DesktopElement,
    )

    state = DesktopAppState(
        app=DesktopAppInfo(app_id="x", name="X", bundle_id="x"),
        title="X",
        screenshot_bytes=b"",
        screenshot_ref="r",
        elements=[
            DesktopElement(
                index=0, role="button", name="Save", x=0, y=0, width=10, height=10
            )
        ],
    )
    assert heuristic_goal_satisfied(
        "click Save",
        {"action": "click", "index": 0},
        state,
    )
    assert not heuristic_goal_satisfied(
        "open preferences",
        {"action": "click", "index": 0},
        state,
    )
    assert heuristic_goal_satisfied(
        "type hello into the field",
        {"action": "type_text", "text": "hello"},
        state,
    )
