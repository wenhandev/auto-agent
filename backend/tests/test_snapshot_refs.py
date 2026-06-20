"""Snapshot element ref tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.perception import (
    ElementSignature,
    IndexedElement,
    Observation,
    elements_from_ax_snapshot,
    resolve_ref,
)


def _observation_with_ref(ref: str = "ref_login") -> Observation:
    return Observation(
        url="https://example.com/login",
        title="Login",
        screenshot_bytes=b"png",
        screenshot_ref="/tmp/fake.png",
        ax_snapshot={},
        elements=[
            IndexedElement(
                index=0,
                role="button",
                name="Sign in",
                signature=ElementSignature(role="button", name="Sign in"),
                ref=ref,
            )
        ],
        page_text_summary="Sign in",
    )


def test_elements_from_ax_snapshot_include_refs_and_indices() -> None:
    elements = elements_from_ax_snapshot(
        {
            "role": "WebArea",
            "name": "",
            "children": [
                {"role": "button", "name": "Sign in"},
                {"role": "textbox", "name": "Email"},
            ],
        }
    )

    assert [el.index for el in elements] == [0, 1]
    assert all(el.ref for el in elements)
    assert elements[0].signature_metadata["role"] == "button"
    assert elements[0].signature_metadata["name"] == "Sign in"


def test_resolve_ref_returns_current_observation_element() -> None:
    observation = _observation_with_ref("ref_login")

    resolved = resolve_ref(observation, "ref_login")

    assert resolved.index == 0
    assert resolved.name == "Sign in"


def test_resolve_ref_rejects_missing_ref() -> None:
    observation = _observation_with_ref("ref_login")

    with pytest.raises(ValueError, match="ref"):
        resolve_ref(observation, "stale-ref")


@pytest.mark.asyncio
async def test_autonomous_click_accepts_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agents.autonomous import AgentDecision, AutonomousAgent, Memory, ToolCall

    locator = MagicMock()
    locator.click = AsyncMock()
    page = MagicMock()
    monkeypatch.setattr("app.agents.autonomous.get_page", AsyncMock(return_value=page))
    monkeypatch.setattr(
        "app.agents.autonomous.resolve_element",
        AsyncMock(return_value=(locator, _observation_with_ref())),
    )

    agent = AutonomousAgent(decide_fn=AsyncMock())
    result = await agent._execute_tool(
        "click_element",
        {"ref": "ref_login"},
        observation=_observation_with_ref(),
        allowed_domains=None,
        memory=Memory(objective="click"),
        page=page,
    )

    assert result["clicked_ref"] == "ref_login"
    locator.click.assert_awaited_once()


@pytest.mark.asyncio
async def test_autonomous_click_rejects_stale_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.agents.autonomous import AutonomousAgent, Memory

    page = MagicMock()
    monkeypatch.setattr("app.agents.autonomous.get_page", AsyncMock(return_value=page))

    agent = AutonomousAgent(decide_fn=AsyncMock())
    result = await agent._execute_tool(
        "click_element",
        {"ref": "missing-ref"},
        observation=_observation_with_ref(),
        allowed_domains=None,
        memory=Memory(objective="click"),
        page=page,
    )

    assert result == {"error": "ref 'missing-ref' unavailable in current observation"}
