"""Tests for agent loop metrics accumulation and API visibility."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.agents.autonomous import AutonomousAgent
from app.db.models import Run, Workflow, WorkflowVersion
from app.db.session import engine
from app.schemas_tasks import TaskResult, TaskSpec
from app.services.agent_loop_metrics import (
    AgentLoopMetrics,
    get_metrics,
    observe_event,
    parse_metrics_json,
    persist_metrics,
    reset_metrics,
    set_metrics,
)
from app.services.tasks import _drive_autonomous_run


def test_metrics_accumulator_tracks_tool_and_cache_counts() -> None:
    metrics = AgentLoopMetrics()
    metrics.record_round()
    metrics.record_tool_result(success=True)
    metrics.record_tool_result(success=False)
    metrics.record_cache(hit=True)
    metrics.record_cache(hit=False)
    metrics.record_computer_use_fallback()
    metrics.record_no_effect()
    summary = metrics.finalize("completed")
    assert summary["rounds"] == 1
    assert summary["tool_successes"] == 1
    assert summary["tool_failures"] == 1
    assert summary["cache_hits"] == 1
    assert summary["cache_misses"] == 1
    assert summary["computer_use_fallbacks"] == 1
    assert summary["no_effect_count"] == 1
    assert summary["stop_reason"] == "completed"


def test_observe_event_maps_vision_and_primitive_events() -> None:
    metrics = AgentLoopMetrics()
    token = set_metrics(metrics)
    try:
        observe_event({"event": "cache_hit"})
        observe_event({"event": "cache_miss"})
        observe_event({"event": "computer_use_action", "action": "click_at"})
        observe_event({
            "event": "vision_step",
            "result": {"clicked_index": 1},
            "action_effect": {"summary": "no visible effect"},
        })
        observe_event({
            "event": "primitive_act",
            "source": "cache",
            "result": {"clicked_index": 0},
        })
    finally:
        reset_metrics(token)
    assert metrics.cache_hits == 2
    assert metrics.cache_misses == 1
    assert metrics.computer_use_fallbacks == 1
    assert metrics.no_effect_count == 1
    assert metrics.tool_successes == 2


@pytest.mark.asyncio
async def test_autonomous_run_emits_and_persists_metrics(monkeypatch) -> None:
    run_id = str(uuid.uuid4())
    wf_id = str(uuid.uuid4())
    ver_id = str(uuid.uuid4())

    async def fake_decide(**kwargs):
        from app.agents.autonomous import AgentDecision

        return AgentDecision(is_finish=True, success=True, summary="done")

    async def fake_reflect(**kwargs):
        return []

    agent = AutonomousAgent(decide_fn=fake_decide, reflect_fn=fake_reflect)
    emitted: list[dict] = []

    async def emit(payload: dict) -> None:
        emitted.append(payload)
        observe_event(payload)

    token = set_metrics(AgentLoopMetrics())
    try:
        metrics = get_metrics()
        assert metrics is not None
        metrics.record_round()
        result = await agent.run_task(
            TaskSpec(objective="test metrics", max_steps=3, max_seconds=30),
            emit,
        )
        summary = metrics.finalize(result.reason or "completed")
    finally:
        reset_metrics(token)

    assert result.success is True
    assert summary["stop_reason"] == "completed"

    with Session(engine) as db:
        run = Run(
            id=run_id,
            workflow_id=wf_id,
            workflow_version_id=ver_id,
            status="running",
            mode="autonomous",
            objective="test",
        )
        db.add(run)
        db.commit()
        persist_metrics(run_id, summary)
        db.refresh(run)
        parsed = parse_metrics_json(run.agent_loop_metrics_json)
        assert parsed is not None
        assert parsed["stop_reason"] == "completed"


@pytest.mark.asyncio
async def test_failed_run_records_no_progress_metrics() -> None:
    metrics = AgentLoopMetrics()
    metrics.record_round()
    metrics.record_no_effect()
    metrics.record_no_effect()
    summary = metrics.finalize("no_progress")
    assert summary["no_effect_count"] == 2
    assert summary["stop_reason"] == "no_progress"


def _seed_autonomous_run(db: Session) -> Run:
    wf = Workflow(name=f"wf-{uuid.uuid4().hex[:8]}")
    db.add(wf)
    db.commit()
    db.refresh(wf)
    ver = WorkflowVersion(
        workflow_id=wf.id,
        version_index=1,
        nodes_json="[]",
        edges_json="[]",
        start_id="start",
        authored_by="manual",
    )
    db.add(ver)
    wf.current_version_id = ver.id
    db.add(wf)
    run = Run(
        workflow_id=wf.id,
        workflow_version_id=ver.id,
        status="queued",
        mode="autonomous",
        objective="metrics api test",
        max_steps=5,
        max_seconds=60,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@pytest.mark.asyncio
async def test_drive_autonomous_run_writes_metrics_event(monkeypatch) -> None:
    async def fake_run_task(spec, emit, *, abort_event=None):
        await emit({"event": "cache_hit"})
        await emit({"event": "vision_step", "result": {"ok": True}})
        return TaskResult(success=True, summary="ok", reason="completed", steps_taken=1)

    monkeypatch.setattr("app.services.tasks.run_autonomous_task", fake_run_task)
    monkeypatch.setattr("app.tools.browser.start_run_trace", AsyncMock())
    monkeypatch.setattr("app.tools.browser.stop_run_trace", AsyncMock())

    with Session(engine) as db:
        run = _seed_autonomous_run(db)
        run_id = run.id

    await _drive_autonomous_run(run_id)

    with Session(engine) as db:
        row = db.get(Run, run_id)
        assert row is not None
        assert row.agent_loop_metrics_json is not None
        metrics = json.loads(row.agent_loop_metrics_json)
        assert metrics["stop_reason"] == "completed"
        assert metrics["cache_hits"] >= 1

    from app.services import runs as run_svc
    from sqlmodel import select
    from app.db.models import RunEvent

    with Session(engine) as db:
        events = db.exec(
            select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
        ).all()
        metric_events = [
            json.loads(e.payload_json)
            for e in events
            if e.event_type == "agent_loop_metrics"
        ]
        assert metric_events
        assert metric_events[-1]["stop_reason"] == "completed"


@pytest.mark.asyncio
async def test_metrics_coexist_with_detailed_events(monkeypatch) -> None:
    async def fake_run_task(spec, emit, *, abort_event=None):
        await emit({"event": "vision_step", "result": {"clicked_index": 0}})
        await emit({"event": "task_finished", "success": True})
        return TaskResult(success=True, summary="ok", reason="completed", steps_taken=1)

    monkeypatch.setattr("app.services.tasks.run_autonomous_task", fake_run_task)
    monkeypatch.setattr("app.tools.browser.start_run_trace", AsyncMock())
    monkeypatch.setattr("app.tools.browser.stop_run_trace", AsyncMock())

    with Session(engine) as db:
        run = _seed_autonomous_run(db)
        run_id = run.id

    await _drive_autonomous_run(run_id)

    from sqlmodel import select
    from app.db.models import RunEvent

    with Session(engine) as db:
        events = db.exec(
            select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
        ).all()
        types = {e.event_type for e in events}
        assert "vision_step" in types or any(
            "vision_step" in json.loads(e.payload_json).get("event", "")
            for e in events
        )
        assert "agent_loop_metrics" in types
