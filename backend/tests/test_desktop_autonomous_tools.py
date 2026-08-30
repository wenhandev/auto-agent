"""Autonomous desktop tool schema + execute dispatch."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.agents.autonomous import AutonomousAgent, Memory, tool_schemas
from app.schemas_tasks import (
    DESKTOP_TOOLS,
    DEFAULT_ALLOWED_TOOLS,
    DEFAULT_DESKTOP_ALLOWED_TOOLS,
)
from app.services.desktop_computer_use.app_lock import reset_app_locks_for_tests
from app.services.desktop_computer_use.auth import reset_auth_store_for_tests
from app.services.desktop_computer_use.factory import set_desktop_backend_for_tests
from app.services.desktop_computer_use.fake import FakeDesktopComputerUseBackend
from app.services.desktop_computer_use.session import set_session_checker_for_tests
from app.services.perception import Observation

async def _noop_decide(**kwargs):  # type: ignore[no-untyped-def]
    from app.agents.autonomous import AgentDecision

    return AgentDecision(thought="", is_finish=True, success=True, summary="ok")


async def _noop_reflect(**kwargs):  # type: ignore[no-untyped-def]
    return []


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


def test_desktop_tools_not_in_browser_default() -> None:
    assert not DESKTOP_TOOLS.intersection(DEFAULT_ALLOWED_TOOLS)
    names = {s["name"] for s in tool_schemas(frozenset(DEFAULT_ALLOWED_TOOLS))}
    assert "list_apps" not in names
    assert "desktop_click" not in names


def test_desktop_tools_in_desktop_default() -> None:
    assert DESKTOP_TOOLS.issubset(set(DEFAULT_DESKTOP_ALLOWED_TOOLS))
    names = {s["name"] for s in tool_schemas(frozenset(DEFAULT_DESKTOP_ALLOWED_TOOLS))}
    assert "list_apps" in names
    assert "desktop_click" in names
    assert "get_app_state" in names


@pytest.mark.asyncio
async def test_execute_desktop_tools(backend: FakeDesktopComputerUseBackend) -> None:
    agent = AutonomousAgent(decide_fn=_noop_decide, reflect_fn=_noop_reflect)
    obs = Observation(
        url="about:blank",
        title="",
        screenshot_bytes=b"",
        screenshot_ref="none",
        ax_snapshot={},
        elements=[],
    )
    page = MagicMock()
    memory = Memory(objective="test")
    listed = await agent._execute_tool(
        "list_apps",
        {},
        observation=obs,
        allowed_domains=None,
        memory=memory,
        page=page,
    )
    assert any(a["name"] == "TextEdit" for a in listed["apps"])

    state = await agent._execute_tool(
        "get_app_state",
        {"app": "TextEdit"},
        observation=obs,
        allowed_domains=None,
        memory=memory,
        page=page,
    )
    assert state["elements"]

    typed = await agent._execute_tool(
        "desktop_type",
        {"app": "TextEdit", "text": "hi", "index": 0},
        observation=obs,
        allowed_domains=None,
        memory=memory,
        page=page,
    )
    assert typed.get("ok") is True
    assert memory.active_desktop_app
    assert memory.desktop_lock_holder
    holder = memory.desktop_lock_holder

    typed2 = await agent._execute_tool(
        "desktop_type",
        {"app": "TextEdit", "text": "!", "index": 0},
        observation=obs,
        allowed_domains=None,
        memory=memory,
        page=page,
    )
    assert typed2.get("ok") is True
    assert memory.desktop_lock_holder == holder


@pytest.mark.asyncio
async def test_perceive_step_uses_desktop_state(
    backend: FakeDesktopComputerUseBackend,
) -> None:
    from app.schemas_tasks import DEFAULT_DESKTOP_ALLOWED_TOOLS

    agent = AutonomousAgent(decide_fn=_noop_decide, reflect_fn=_noop_reflect)
    memory = Memory(objective="desktop", active_desktop_app="TextEdit")
    page = MagicMock()
    obs = await agent._perceive_step(
        page,
        memory,
        allowed=frozenset(DEFAULT_DESKTOP_ALLOWED_TOOLS),
        ref_hint="t",
    )
    assert obs.url.startswith("desktop://")
    assert obs.elements
    page.evaluate.assert_not_called()


def test_desktop_click_ignores_browser_observation_index() -> None:
    from app.agents.autonomous_guardrails import is_destructive_action
    from app.services.perception import ElementSignature, IndexedElement

    browser_obs = Observation(
        url="https://example.com",
        title="Shop",
        screenshot_bytes=b"",
        screenshot_ref="b",
        ax_snapshot={},
        elements=[
            IndexedElement(
                index=0,
                role="button",
                name="Buy Now",
                signature=ElementSignature(role="button", name="Buy Now"),
            )
        ],
    )
    # Without desktop:// observation, index clicks are high-risk (not browser-mapped).
    assert (
        is_destructive_action(
            "desktop_click",
            {"app": "TextEdit", "index": 0},
            observation=browser_obs,
        )
        is True
    )


def test_desktop_click_uses_desktop_observation_label() -> None:
    from app.agents.autonomous_guardrails import is_destructive_action
    from app.services.perception import ElementSignature, IndexedElement

    desktop_obs = Observation(
        url="desktop://com.apple.TextEdit",
        title="TextEdit",
        screenshot_bytes=b"",
        screenshot_ref="d",
        ax_snapshot={},
        elements=[
            IndexedElement(
                index=0,
                role="button",
                name="Buy Now",
                signature=ElementSignature(role="button", name="Buy Now"),
            )
        ],
    )
    assert (
        is_destructive_action(
            "desktop_click",
            {"app": "TextEdit", "index": 0},
            observation=desktop_obs,
        )
        is True
    )


@pytest.mark.asyncio
async def test_perceive_step_keeps_desktop_url_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.schemas_tasks import DEFAULT_DESKTOP_ALLOWED_TOOLS

    agent = AutonomousAgent(decide_fn=_noop_decide, reflect_fn=_noop_reflect)
    memory = Memory(objective="desktop", active_desktop_app="TextEdit")

    class _Boom:
        async def get_app_state(self, app: str):  # type: ignore[no-untyped-def]
            raise RuntimeError("ax unavailable")

    monkeypatch.setattr(
        "app.services.desktop_computer_use.resolve_desktop_backend",
        lambda: _Boom(),
    )
    obs = await agent._perceive_step(
        MagicMock(),
        memory,
        allowed=frozenset(DEFAULT_DESKTOP_ALLOWED_TOOLS),
        ref_hint="t",
    )
    assert obs.url.startswith("desktop://")
    assert obs.elements == []
