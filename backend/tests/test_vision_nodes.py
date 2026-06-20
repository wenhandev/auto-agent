"""Vision node executor and bounded-loop tests with mocked agent/LLM."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app import executor
from app.agents.vision import VisionAgent
from app.schemas import Node


async def _capture_emit() -> tuple[Any, list[dict]]:
    events: list[dict] = []

    async def emit(event: str, *, node_id: str | None = None, **extra: Any) -> None:
        payload = {"event": event, "node_id": node_id}
        payload.update(extra)
        events.append(payload)

    return emit, events


@pytest.mark.asyncio
async def test_executor_vision_navigate_emits_vision_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_navigate(self, goal, **kwargs):
        on_step = kwargs.get("on_step")
        if on_step:
            await on_step(
                {
                    "step_index": 1,
                    "thought": "click cart",
                    "action": "click_element",
                    "target_index": 2,
                    "screenshot_ref": "/tmp/step1.png",
                }
            )
        return {"completed": True, "summary": "done", "steps": 1}

    monkeypatch.setattr(VisionAgent, "run_navigate", fake_run_navigate)

    emit, events = await _capture_emit()
    node = Node(
        id="vn1",
        type="vision_navigate",
        label="reach goal",
        params={"goal": "add item to cart", "max_steps": 4},
    )
    result = await executor._run_node(node, emit)

    assert result["completed"]
    vision_steps = [e for e in events if e["event"] == "vision_step"]
    assert len(vision_steps) == 1
    assert vision_steps[0]["action"] == "click_element"
    assert vision_steps[0]["target_index"] == 2


@pytest.mark.asyncio
async def test_fuzzy_action_alias_uses_vision_navigate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    async def fake_run_navigate(self, goal, **kwargs):
        seen["goal"] = goal
        return {"completed": True, "summary": "ok", "steps": 1}

    monkeypatch.setattr(VisionAgent, "run_navigate", fake_run_navigate)

    emit, _ = await _capture_emit()
    node = Node(
        id="fz1",
        type="fuzzy_action",
        label="fuzzy",
        params={"instruction": "find the title"},
    )
    await executor._run_node(node, emit)
    assert seen["goal"] == "find the title"


@pytest.mark.asyncio
async def test_bounded_loop_max_steps_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_navigate passes max_steps budget and returns non-crashing outcome."""
    captured: dict[str, Any] = {}

    async def fake_run_loop(self, **kwargs):
        captured.update(kwargs)
        return {
            "completed": False,
            "reason": "max_steps_reached",
            "steps": kwargs["max_steps"],
            "last_observation": "stuck",
        }

    monkeypatch.setattr(VisionAgent, "_run_loop", fake_run_loop)
    monkeypatch.setattr("app.agents.vision.llm_is_configured", lambda: True)

    agent = VisionAgent()
    result = await agent.run_navigate("never finishes", max_steps=2)

    assert captured["max_steps"] == 2
    assert result["completed"] is False
    assert result["reason"] == "max_steps_reached"


@pytest.mark.asyncio
async def test_run_extract_uses_vision_max_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_run_loop(self, **kwargs):
        captured.update(kwargs)
        return {"completed": True, "data": {"title": "ok"}, "steps": 1}

    monkeypatch.setattr(VisionAgent, "_run_loop", fake_run_loop)
    monkeypatch.setattr("app.agents.vision.llm_is_configured", lambda: True)

    agent = VisionAgent()
    await agent.run_extract("page title")
    assert captured["max_steps"] == 8
    assert captured["mode"] == "extract"


@pytest.mark.asyncio
async def test_executor_vision_extract_fails_on_max_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_extract(self, instruction, **kwargs):
        return {
            "completed": False,
            "reason": "max_steps_reached",
            "steps": 8,
            "last_observation": '{"status": "max_steps_exceeded"}',
        }

    monkeypatch.setattr(VisionAgent, "run_extract", fake_run_extract)

    emit, _ = await _capture_emit()
    node = Node(
        id="ve1",
        type="vision_extract",
        label="extract stories",
        params={"instruction": "top 5 stories", "schema": {"type": "object"}},
    )
    with pytest.raises(RuntimeError, match="vision_extract failed: max_steps_reached"):
        await executor._run_node(node, emit)
