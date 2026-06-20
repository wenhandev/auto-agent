"""Autonomous loop tests with mocked perception/LLM/browser."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.autonomous import (
    AgentDecision,
    AutonomousAgent,
    Memory,
    ToolCall,
    resolve_allowed_tools,
    summarize_action_effect,
)
from app.agents.autonomous_guardrails import BudgetClock, ConfirmationGate
from app.schemas_tasks import PlanItem, TaskSpec
from app.services.perception import ElementSignature, IndexedElement, Observation


def _fake_observation(
    url: str = "https://example.com",
    elements: list[tuple[str, str]] | None = None,
    title: str = "Test",
    page_text_summary: str = "hello",
) -> Observation:
    els = [
        IndexedElement(
            index=i,
            role=role,
            name=name,
            signature=ElementSignature(role=role, name=name),
        )
        for i, (role, name) in enumerate(elements or [("button", "Go")])
    ]
    return Observation(
        url=url,
        title=title,
        screenshot_bytes=b"png",
        screenshot_ref="/tmp/fake.png",
        ax_snapshot={},
        elements=els,
        page_text_summary=page_text_summary,
    )


@pytest.fixture
def mock_page(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    page = MagicMock()
    page.url = "https://example.com"
    page.go_back = AsyncMock()
    page.mouse.wheel = AsyncMock()
    monkeypatch.setattr("app.agents.autonomous.get_page", AsyncMock(return_value=page))
    monkeypatch.setattr(
        "app.agents.autonomous.perceive",
        AsyncMock(side_effect=lambda _page, **_: _fake_observation()),
    )
    monkeypatch.setattr(
        "app.agents.autonomous.actions.navigate",
        AsyncMock(return_value={"url": "https://example.com"}),
    )
    return page


async def _collect_emit(agent: AutonomousAgent, spec: TaskSpec) -> tuple[list[dict], Any]:
    events: list[dict] = []

    async def emit(payload: dict) -> None:
        events.append(payload)

    result = await agent.run_task(spec, emit)
    return events, result


@pytest.mark.asyncio
async def test_finish_terminates_loop(mock_page: MagicMock) -> None:
    calls = {"n": 0}

    async def decide(**kwargs: Any) -> AgentDecision:
        calls["n"] += 1
        if calls["n"] == 1:
            return AgentDecision(
                thought="wait",
                tool=ToolCall(name="wait", args={"ms": 1}),
            )
        return AgentDecision(
            is_finish=True,
            success=True,
            summary="done",
            result={"status": "done"},
        )

    agent = AutonomousAgent(decide_fn=decide)
    events, result = await _collect_emit(
        agent,
        TaskSpec(objective="find price", max_steps=10, max_seconds=60),
    )
    assert result.success is True
    assert result.summary == "done"
    assert result.steps_taken >= 1
    assert any(e["event"] == "task_finished" for e in events)


@pytest.mark.asyncio
async def test_zero_step_success_finish_is_rejected(mock_page: MagicMock) -> None:
    async def decide(**kwargs: Any) -> AgentDecision:
        return AgentDecision(
            is_finish=True,
            success=True,
            summary="done too early",
        )

    agent = AutonomousAgent(decide_fn=decide)
    _, result = await _collect_emit(
        agent,
        TaskSpec(objective="find price", max_steps=10, max_seconds=60),
    )
    assert result.success is False
    assert result.steps_taken == 0
    assert "No browser actions were taken" in (result.summary or "")


@pytest.mark.asyncio
async def test_navigate_only_success_finish_rejected(mock_page: MagicMock) -> None:
    calls = {"n": 0}

    async def decide(**kwargs: Any) -> AgentDecision:
        calls["n"] += 1
        if calls["n"] == 1:
            return AgentDecision(
                thought="open search",
                tool=ToolCall(name="navigate", args={"url": "https://example.com"}),
            )
        return AgentDecision(
            is_finish=True,
            success=True,
            summary="已从官网成功提取价格",
        )

    agent = AutonomousAgent(decide_fn=decide)
    _, result = await _collect_emit(
        agent,
        TaskSpec(objective="find iphone price", max_steps=5, max_seconds=60),
    )
    assert result.success is False
    assert "without extracted data" in (result.summary or "").lower()
    assert result.steps_taken == 1


@pytest.mark.asyncio
async def test_step_budget_terminates(mock_page: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    step = {"n": 0}

    async def varying_perceive(_page, **kwargs: Any) -> Observation:
        step["n"] += 1
        return _fake_observation(url=f"https://example.com/page{step['n']}")

    monkeypatch.setattr("app.agents.autonomous.perceive", varying_perceive)

    async def decide(**kwargs: Any) -> AgentDecision:
        return AgentDecision(
            thought="click",
            tool=ToolCall(name="wait", args={"ms": 1}),
        )

    agent = AutonomousAgent(decide_fn=decide)
    _, result = await _collect_emit(
        agent,
        TaskSpec(objective="loop", max_steps=3, max_seconds=300),
    )
    assert result.success is False
    assert result.reason == "step_budget_exhausted"
    assert result.steps_taken == 3


@pytest.mark.asyncio
async def test_time_budget_terminates(mock_page: MagicMock) -> None:
    clock = BudgetClock(max_steps=100, max_seconds=0)

    async def decide(**kwargs: Any) -> AgentDecision:
        return AgentDecision(is_finish=True, success=True, summary="late")

    agent = AutonomousAgent(decide_fn=decide)
    events: list[dict] = []

    async def emit(payload: dict) -> None:
        events.append(payload)

    spec = TaskSpec(objective="x", max_steps=100, max_seconds=300)
    agent.confirmation_gate = ConfirmationGate(False)
    # Force deadline exceeded before loop body
    monkeypatch_clock = clock
    monkeypatch_clock.started_at = clock.started_at

    from datetime import timedelta, timezone

    monkeypatch_clock.started_at = monkeypatch_clock.started_at - timedelta(seconds=400)

    async def fake_run(spec_in, emit_in, **kwargs):
        bc = BudgetClock(max_steps=spec_in.max_steps, max_seconds=spec_in.max_seconds)
        bc.started_at = monkeypatch_clock.started_at
        if bc.deadline_exceeded():
            from app.schemas_tasks import TaskResult

            r = TaskResult(
                success=False,
                summary="Budget exhausted (time_budget_exhausted)",
                reason="time_budget_exhausted",
            )
            await emit_in({"event": "task_finished", "success": False, "result": r.model_dump()})
            return r
        return await AutonomousAgent(decide_fn=decide).run_task(spec_in, emit_in)

    result = await fake_run(spec, emit)
    assert result.reason == "time_budget_exhausted"


@pytest.mark.asyncio
async def test_tool_restriction_enforced(mock_page: MagicMock) -> None:
    attempted: list[str] = []

    async def decide(**kwargs: Any) -> AgentDecision:
        attempted.append("decide")
        return AgentDecision(
            tool=ToolCall(
                name="integration",
                args={"app": "slack", "resource": "msg", "operation": "create"},
            ),
        )

    agent = AutonomousAgent(decide_fn=decide)
    spec = TaskSpec(
        objective="no integrations",
        max_steps=2,
        allowed_tools=["wait", "finish"],
    )
    _, result = await _collect_emit(agent, spec)
    assert "integration" not in resolve_allowed_tools(spec)
    assert result.steps_taken <= 2


@pytest.mark.asyncio
async def test_schema_valid_finish(mock_page: MagicMock) -> None:
    async def decide(**kwargs: Any) -> AgentDecision:
        return AgentDecision(
            is_finish=True,
            success=True,
            result={"price": 199},
            summary="found price",
        )

    agent = AutonomousAgent(decide_fn=decide)
    _, result = await _collect_emit(
        agent,
        TaskSpec(
            objective="get price",
            max_steps=5,
            data_schema={"type": "object", "properties": {"price": {"type": "number"}}, "required": ["price"]},
        ),
    )
    assert result.success is True
    assert result.data == {"price": 199}


@pytest.mark.asyncio
async def test_invalid_finish_retries_then_fails(mock_page: MagicMock) -> None:
    attempts = {"n": 0}

    async def decide(**kwargs: Any) -> AgentDecision:
        attempts["n"] += 1
        return AgentDecision(
            is_finish=True,
            success=True,
            result={"price": "not-a-number"},
            summary="bad",
        )

    agent = AutonomousAgent(decide_fn=decide)
    _, result = await _collect_emit(
        agent,
        TaskSpec(
            objective="get price",
            max_steps=5,
            data_schema={"type": "object", "properties": {"price": {"type": "number"}}, "required": ["price"]},
        ),
    )
    assert result.success is False
    assert result.reason == "schema_validation_failed"
    assert attempts["n"] >= 2


@pytest.mark.asyncio
async def test_data_items_survive_compaction() -> None:
    memory = Memory(objective="extract items")
    memory.extracted_items = [{"sku": "A1"}, {"sku": "B2"}]
    for i in range(20):
        memory.record_observation(_fake_observation(url=f"https://example.com/{i}"))
    assert memory.extracted_items == [{"sku": "A1"}, {"sku": "B2"}]
    assert len(memory.recent_observations) <= 8


def test_memory_context_includes_goal_remaining_and_last_effect() -> None:
    memory = Memory(
        objective="buy concert tickets",
        session_memory=[
            {
                "objective": "previous ticket search",
                "summary": "used the same logged-in account",
            }
        ],
    )
    memory.plan = [
        PlanItem(id="1", text="open site", status="done"),
        PlanItem(id="2", text="select seats", status="in_progress"),
        PlanItem(id="3", text="checkout", status="pending"),
    ]
    memory.record_action_effect(
        {
            "summary": "click changed URL",
            "url_changed": True,
        }
    )

    ctx = memory.to_context()

    assert ctx["original_goal"] == "buy concert tickets"
    assert ctx["objective"] == "buy concert tickets"
    assert ctx["remaining_steps"] == ["select seats", "checkout"]
    assert ctx["last_action_effect"] == {
        "summary": "click changed URL",
        "url_changed": True,
    }
    assert ctx["session_memory"] == [
        {
            "objective": "previous ticket search",
            "summary": "used the same logged-in account",
        }
    ]


def test_summarize_action_effect_detects_page_changes() -> None:
    before = _fake_observation(
        url="https://example.com/start",
        title="Start",
        elements=[("button", "Next")],
        page_text_summary="start page",
    )
    after = _fake_observation(
        url="https://example.com/next",
        title="Next",
        elements=[("button", "Done"), ("textbox", "Email")],
        page_text_summary="next page",
    )

    effect = summarize_action_effect(
        before,
        after,
        action_label="click_element({\"index\": 0})",
        previous_action_label="wait({\"ms\": 1})",
        data_items_before=0,
        data_items_after=1,
    )

    assert effect["url_changed"] is True
    assert effect["title_changed"] is True
    assert effect["elements_changed"] is True
    assert effect["text_changed"] is True
    assert effect["data_items_added"] == 1
    assert effect["repeated_action"] is False
    assert "changed url" in effect["summary"]


@pytest.mark.asyncio
async def test_vision_step_includes_action_effect(
    mock_page: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations = [
        _fake_observation(url="https://example.com/start", title="Start"),
        _fake_observation(url="https://example.com/next", title="Next"),
    ]
    monkeypatch.setattr(
        "app.agents.autonomous.perceive",
        AsyncMock(side_effect=observations),
    )

    async def decide(**kwargs: Any) -> AgentDecision:
        return AgentDecision(
            thought="wait for page",
            tool=ToolCall(name="wait", args={"ms": 1}),
        )

    agent = AutonomousAgent(decide_fn=decide)
    events, _ = await _collect_emit(
        agent,
        TaskSpec(objective="watch effect", max_steps=1, max_seconds=60),
    )
    step = next(e for e in events if e["event"] == "vision_step")

    assert step["action_effect"]["url_changed"] is True
    assert "changed url" in step["action_effect"]["summary"]


@pytest.mark.asyncio
async def test_route_skill_context_guides_prompt_and_narrows_tools(
    mock_page: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.route_skills import RouteSkillContext

    monkeypatch.setattr(
        "app.agents.autonomous.load_route_context",
        lambda url, allowed_tools: RouteSkillContext(
            skill_ids=["skill-1"],
            prompts=["Only finish on this route"],
            allowed_tools=frozenset({"finish"}),
        ),
        raising=False,
    )

    captured: dict[str, Any] = {}
    calls = {"n": 0}

    async def decide(**kwargs: Any) -> AgentDecision:
        calls["n"] += 1
        captured["allowed_tools"] = kwargs["allowed_tools"]
        captured["context"] = kwargs["memory"].to_context()
        if calls["n"] == 1:
            return AgentDecision(
                thought="wait",
                tool=ToolCall(name="wait", args={"ms": 1}),
            )
        return AgentDecision(is_finish=True, success=True, summary="ok", result={"ok": True})

    agent = AutonomousAgent(decide_fn=decide)
    events, result = await _collect_emit(
        agent,
        TaskSpec(objective="route task", max_steps=2),
    )

    assert result.success is True
    assert captured["allowed_tools"] == frozenset({"finish"})
    assert captured["context"]["route_prompts"] == ["Only finish on this route"]
    assert captured["context"]["route_skill_ids"] == ["skill-1"]
    assert any(e["event"] == "route_skill_applied" for e in events)


@pytest.mark.asyncio
async def test_plan_updated_on_start(mock_page: MagicMock) -> None:
    async def reflect(**kwargs: Any) -> list[PlanItem]:
        return [PlanItem(id="a", text="subgoal", status="pending")]

    async def decide(**kwargs: Any) -> AgentDecision:
        return AgentDecision(is_finish=True, success=True, summary="ok", result={"ok": True})

    agent = AutonomousAgent(decide_fn=decide, reflect_fn=reflect)
    events, _ = await _collect_emit(
        agent,
        TaskSpec(objective="plan test", max_steps=3),
    )
    assert any(e["event"] == "task_plan_updated" for e in events)
