"""Autonomous guardrail tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.autonomous import AgentDecision, AutonomousAgent, ToolCall
from app.agents.autonomous_guardrails import (
    BudgetClock,
    ConfirmationGate,
    ProgressTracker,
    check_navigation,
    is_destructive_action,
)
from app.schemas_tasks import TaskSpec
from app.services.perception import ElementSignature, IndexedElement, Observation


def _obs(
    url: str = "https://example.com",
    elements: list[tuple[str, str]] | None = None,
) -> Observation:
    els = [
        IndexedElement(
            index=i,
            role=role,
            name=name,
            signature=ElementSignature(role=role, name=name),
        )
        for i, (role, name) in enumerate(elements or [])
    ]
    return Observation(
        url=url,
        title="T",
        screenshot_bytes=b"x",
        screenshot_ref="/tmp/x.png",
        ax_snapshot={},
        elements=els,
    )


def test_off_allowlist_navigation_blocked() -> None:
    err = check_navigation("https://evil.test/page", ["example.com"])
    assert err is not None
    assert "evil.test" in err
    assert "allowed_domains" in err


def test_allowlist_permits_host() -> None:
    assert check_navigation("https://www.example.com", ["example.com"]) is None


def test_time_budget_enforced() -> None:
    from datetime import timedelta, timezone

    clock = BudgetClock(max_steps=50, max_seconds=1)
    clock.started_at = clock.started_at - timedelta(seconds=5)
    assert clock.deadline_exceeded() is True


def test_purchase_action_classified_destructive() -> None:
    obs = _obs(elements=[("button", "Checkout and Pay")])
    assert is_destructive_action("click_element", {"index": 0}, observation=obs)


def test_integration_write_classified_destructive() -> None:
    assert is_destructive_action(
        "integration",
        {"operation": "create", "app": "slack"},
    )


@pytest.mark.asyncio
async def test_purchase_pause_when_confirmation_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paused: list[str] = []

    async def reject(_desc: str, _action: dict) -> bool:
        return False

    gate = ConfirmationGate(True, handler=reject)
    obs = _obs(elements=[("button", "Buy Now")])

    allowed, reason = await gate.check(
        "click_element",
        {"index": 0},
        observation=obs,
    )
    assert allowed is False
    assert reason is not None


@pytest.mark.asyncio
async def test_integration_write_pause_under_confirmation() -> None:
    events: list[str] = []

    async def reject(desc: str, _action: dict) -> bool:
        events.append(desc)
        return False

    gate = ConfirmationGate(True, handler=reject)
    allowed, _ = await gate.check(
        "integration",
        {"app": "slack", "resource": "m", "operation": "create"},
    )
    assert allowed is False
    assert events


def test_no_progress_abort_diagnostic() -> None:
    tracker = ProgressTracker(threshold=3)
    obs = _obs(url="https://example.com", elements=[("button", "Go")])
    diag = None
    for _ in range(3):
        diag = tracker.record(obs, action_label="click_element(index=0)", data_items_count=0)
    assert diag is not None
    assert "no progress" in diag
    assert "click_element" in diag


@pytest.mark.asyncio
async def test_off_allowlist_blocks_navigate_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    page.url = "https://example.com"
    monkeypatch.setattr("app.agents.autonomous.get_page", AsyncMock(return_value=page))
    monkeypatch.setattr(
        "app.agents.autonomous.perceive",
        AsyncMock(return_value=_obs()),
    )

    async def decide(**kwargs: Any) -> AgentDecision:
        return AgentDecision(
            tool=ToolCall(name="navigate", args={"url": "https://evil.test"}),
        )

    async def then_finish(**kwargs: Any) -> AgentDecision:
        return AgentDecision(is_finish=True, success=False, summary="giving up")

    seq = [
        AgentDecision(tool=ToolCall(name="navigate", args={"url": "https://evil.test"})),
        AgentDecision(is_finish=True, success=False, summary="giving up"),
    ]
    idx = {"i": 0}

    async def decide_seq(**kwargs: Any) -> AgentDecision:
        d = seq[min(idx["i"], len(seq) - 1)]
        idx["i"] += 1
        return d

    agent = AutonomousAgent(decide_fn=decide_seq)
    events: list[dict] = []

    async def emit(payload: dict) -> None:
        events.append(payload)

    result = await agent.run_task(
        TaskSpec(
            objective="stay on site",
            max_steps=5,
            allowed_domains=["example.com"],
        ),
        emit,
    )
    vision = [e for e in events if e.get("event") == "vision_step"]
    assert any(
        isinstance(e.get("result"), dict) and "blocked" in str(e["result"].get("error", ""))
        for e in vision
    )
