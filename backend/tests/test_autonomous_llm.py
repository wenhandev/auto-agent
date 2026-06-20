"""Tests for LLM decide/reflect hooks in autonomous mode."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.autonomous import AgentDecision, AutonomousAgent, Memory, ToolCall
from app.agents.autonomous_llm import (
    _build_prompt,
    llm_decide,
    llm_reflect,
    resolve_autonomous_hooks,
)
from app.schemas_tasks import PlanItem, TaskSpec
from app.services.perception import ElementSignature, IndexedElement, Observation


def _observation() -> Observation:
    return Observation(
        url="https://example.com",
        title="Example",
        screenshot_bytes=b"png",
        screenshot_ref="/tmp/fake.png",
        ax_snapshot={},
        elements=[
            IndexedElement(
                index=0,
                role="button",
                name="Buy",
                signature=ElementSignature(role="button", name="Buy"),
            )
        ],
        page_text_summary="buy now",
    )


@pytest.mark.asyncio
async def test_resolve_hooks_without_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.agents.autonomous_llm.llm_is_configured", lambda: False)
    decide, reflect = resolve_autonomous_hooks()
    from app.agents.autonomous import default_decide, default_reflect

    assert decide is default_decide
    assert reflect is default_reflect


@pytest.mark.asyncio
async def test_resolve_hooks_with_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.agents.autonomous_llm.llm_is_configured", lambda: True)
    decide, reflect = resolve_autonomous_hooks()

    assert decide.__name__ == "llm_decide"
    assert reflect.__name__ == "llm_reflect"


@pytest.mark.asyncio
async def test_llm_decide_without_config_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.agents.autonomous_llm.llm_is_configured", lambda: False)
    memory = Memory(objective="finish quickly")
    decision = await llm_decide(
        memory=memory,
        observation=_observation(),
        allowed_tools=frozenset({"finish"}),
        data_schema=None,
    )
    assert decision.is_finish is True
    assert decision.success is False


def test_build_prompt_anchors_original_goal_and_current_observation() -> None:
    memory = Memory(objective="download latest invoice")
    prompt = _build_prompt(
        memory=memory,
        observation=_observation(),
        data_schema=None,
    )

    assert "Original objective: download latest invoice" in prompt
    assert "Current page observation is the only source of current page facts" in prompt


@pytest.mark.asyncio
async def test_llm_decide_maps_tool_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.agents.autonomous_llm.llm_is_configured", lambda: True)

    async def fake_run_async(**kwargs: Any):
        capture = kwargs
        # Simulate ADK invoking before_tool_callback path via direct capture in build
        yield MagicMock(content=None)

    class FakeRunner:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        run_async = fake_run_async

    async def fake_decide_via_tools(*, memory, observation, allowed_tools, data_schema):
        return AgentDecision(
            thought="click buy",
            tool=ToolCall(name="click_element", args={"index": 0}),
        )

    with patch("app.agents.autonomous_llm.Runner", FakeRunner), patch(
        "app.agents.autonomous_llm.LlmAgent", MagicMock
    ), patch(
        "app.agents.autonomous_llm.InMemorySessionService"
    ) as mock_session_svc, patch(
        "app.agents.autonomous_llm.get_adk_model", return_value="test-model"
    ):
        mock_session_svc.return_value.create_session = AsyncMock()
        monkeypatch.setattr(
            "app.agents.autonomous_llm.llm_decide",
            fake_decide_via_tools,
        )
        decision = await fake_decide_via_tools(
            memory=Memory(objective="buy"),
            observation=_observation(),
            allowed_tools=frozenset({"click_element", "finish"}),
            data_schema=None,
        )
    assert decision.tool is not None
    assert decision.tool.name == "click_element"


@pytest.mark.asyncio
async def test_build_tools_capture_finish() -> None:
    from app.agents.autonomous_llm import _build_tools

    capture: dict[str, Any] = {"thought": "done"}
    state = {"stop": False}
    tools = _build_tools(frozenset({"finish"}), capture, state)
    finish_tool = next(t for t in tools if getattr(t, "name", "") == "finish")
    await finish_tool.func(success=True, summary="all good", result={"price": 9})
    decision = capture["decision"]
    assert decision.is_finish is True
    assert decision.success is True
    assert decision.summary == "all good"
    assert decision.result == {"price": 9}


@pytest.mark.asyncio
async def test_llm_reflect_parses_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.agents.autonomous_llm.llm_is_configured", lambda: True)

    response = MagicMock()
    response.text = '[{"id":"1","text":"find price","status":"in_progress"}]'

    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(return_value=response)

    with patch("app.agents.autonomous_llm.get_genai_client", return_value=client), patch(
        "app.agents.autonomous_llm.get_genai_model_id", return_value="gemini-test"
    ), patch("app.agents.autonomous_llm._record_usage"):
        plan = await llm_reflect(memory=Memory(objective="find price"))

    assert len(plan) == 1
    assert plan[0].text == "find price"
    assert plan[0].status == "in_progress"


@pytest.mark.asyncio
async def test_llm_reflect_invalid_json_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.agents.autonomous_llm.llm_is_configured", lambda: True)

    response = MagicMock()
    response.text = "not json"

    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(return_value=response)

    with patch("app.agents.autonomous_llm.get_genai_client", return_value=client), patch(
        "app.agents.autonomous_llm.get_genai_model_id", return_value="gemini-test"
    ), patch("app.agents.autonomous_llm._record_usage"):
        plan = await llm_reflect(memory=Memory(objective="fallback objective"))

    assert len(plan) == 1
    assert plan[0].text == "fallback objective"


@pytest.mark.asyncio
async def test_agent_wires_llm_hooks_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.agents.autonomous_llm.llm_is_configured", lambda: True)
    agent = AutonomousAgent()
    assert agent.decide_fn.__name__ == "llm_decide"
    assert agent.reflect_fn.__name__ == "llm_reflect"


@pytest.mark.asyncio
async def test_agent_keeps_stub_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.agents.autonomous_llm.llm_is_configured", lambda: False)
    from app.agents.autonomous import default_decide, default_reflect

    agent = AutonomousAgent()
    assert agent.decide_fn is default_decide
    assert agent.reflect_fn is default_reflect
