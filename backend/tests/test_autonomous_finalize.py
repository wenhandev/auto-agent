"""Autonomous run finalize: one terminal write, hub-visible event, end_run."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlmodel import Session, select

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.models import Run, RunEvent, Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.schemas_tasks import TaskResult
from app.services import artifact_context
from app.services import runs as run_svc
from app.services.tasks import _drive_autonomous_run
from app.services.turn_finalize import finalize_autonomous_run
from app.worker.runtime import WorkerRuntime


@pytest.fixture(autouse=True)
def _clean_process_state():
    init_db()
    yield
    artifact_context.clear_run_context()
    run_svc.reset_dispatcher_for_tests()


def _seed_autonomous_run(session: Session, *, status: str = "queued") -> Run:
    wf = Workflow(name=f"wf-finalize-{uuid.uuid4().hex[:8]}")
    session.add(wf)
    session.commit()
    session.refresh(wf)
    ver = WorkflowVersion(
        workflow_id=wf.id,
        version_index=1,
        nodes_json="[]",
        edges_json="[]",
        start_id="start",
        authored_by="manual",
    )
    session.add(ver)
    session.commit()
    session.refresh(ver)
    wf.current_version_id = ver.id
    session.add(wf)
    run = Run(
        workflow_id=wf.id,
        workflow_version_id=ver.id,
        status=status,
        mode="autonomous",
        objective="finalize contract",
        max_steps=5,
        max_seconds=60,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _delete_run_graph(session: Session, run_id: str, workflow_id: str, version_id: str) -> None:
    for ev in session.exec(select(RunEvent).where(RunEvent.run_id == run_id)).all():
        session.delete(ev)
    row = session.get(Run, run_id)
    if row is not None:
        session.delete(row)
    ver = session.get(WorkflowVersion, version_id)
    if ver is not None:
        session.delete(ver)
    wf = session.get(Workflow, workflow_id)
    if wf is not None:
        session.delete(wf)
    session.commit()


@pytest.fixture
def seeded_run():
    with Session(engine) as session:
        run = _seed_autonomous_run(session, status="queued")
        ids = (run.id, run.workflow_id, run.workflow_version_id)
    yield ids
    run_svc.reset_dispatcher_for_tests()
    with Session(engine) as session:
        _delete_run_graph(session, ids[0], ids[1], ids[2])


@pytest.mark.asyncio
async def test_cloud_success_writes_result_and_calls_end_run(monkeypatch, seeded_run):
    run_id, _, _ = seeded_run

    async def fake_run_task(spec, emit, *, abort_event=None):
        return TaskResult(success=True, summary="ok", reason="completed", steps_taken=1)

    end_run = AsyncMock()
    monkeypatch.setattr("app.services.tasks.run_autonomous_task", fake_run_task)
    monkeypatch.setattr("app.tools.browser.start_run_trace", AsyncMock())
    monkeypatch.setattr("app.tools.browser.stop_run_trace", AsyncMock())
    monkeypatch.setattr("app.tools.browser.end_run", end_run)

    await _drive_autonomous_run(run_id)

    with Session(engine) as session:
        row = session.get(Run, run_id)
        assert row is not None
        assert row.status == "completed"
        assert row.finished_at is not None
        assert row.result_json is not None
        dumped = json.loads(row.result_json)
        assert dumped["success"] is True
        assert dumped["summary"] == "ok"
    end_run.assert_awaited()


@pytest.mark.asyncio
async def test_worker_success_emits_terminal_and_calls_end_run(monkeypatch):
    sent: list[dict] = []

    async def send(frame: dict) -> None:
        sent.append(frame)

    async def fake_run_task(spec, emit, *, abort_event=None):
        return TaskResult(success=True, summary="ok", reason="completed", steps_taken=2)

    end_run = AsyncMock()
    monkeypatch.setattr("app.agents.autonomous.run_task", fake_run_task)
    monkeypatch.setattr("app.tools.browser.start_run_trace", AsyncMock())
    monkeypatch.setattr("app.tools.browser.stop_run_trace", AsyncMock())
    monkeypatch.setattr("app.tools.browser.end_run", end_run)

    runtime = WorkerRuntime(send=send)
    await runtime._handle_autonomous_execute(
        f"run-worker-{uuid.uuid4().hex[:8]}",
        {"objective": "do it", "max_steps": 3},
    )

    terminals = [
        frame["payload"]["event"]
        for frame in sent
        if frame.get("type") == "run_event"
        and frame.get("payload", {}).get("event")
        in ("run_completed", "run_failed", "run_aborted")
    ]
    assert terminals == ["run_completed"]
    output = next(
        frame["payload"]["output"]
        for frame in sent
        if frame.get("type") == "run_event"
        and frame.get("payload", {}).get("event") == "run_completed"
    )
    assert output["success"] is True
    assert output["steps_taken"] == 2
    end_run.assert_awaited()
    assert runtime.active_runs == 0


@pytest.mark.asyncio
async def test_second_finalize_is_noop_when_finished_at_set(monkeypatch, seeded_run):
    run_id, _, _ = seeded_run
    result = TaskResult(success=True, summary="ok", reason="completed", steps_taken=1)
    emitted: list[dict] = []

    async def emit(payload: dict) -> None:
        emitted.append(payload)

    end_run = AsyncMock()
    monkeypatch.setattr("app.tools.browser.stop_run_trace", AsyncMock())
    monkeypatch.setattr("app.tools.browser.end_run", end_run)

    first = await finalize_autonomous_run(
        run_id,
        result,
        terminal_error=None,
        emit=emit,
        metrics=None,
    )
    assert first == "run_completed"
    first_count = len(emitted)
    end_run.assert_awaited_once()

    with Session(engine) as session:
        row = session.get(Run, run_id)
        assert row is not None
        finished_at = row.finished_at
        result_json = row.result_json

    second = await finalize_autonomous_run(
        run_id,
        TaskResult(success=False, summary="nope", reason="error", steps_taken=0),
        terminal_error="should not apply",
        emit=emit,
        metrics=None,
    )
    assert second == "run_completed"
    assert len(emitted) == first_count
    end_run.assert_awaited_once()

    with Session(engine) as session:
        row = session.get(Run, run_id)
        assert row is not None
        assert row.status == "completed"
        assert row.finished_at == finished_at
        assert row.result_json == result_json


@pytest.mark.asyncio
async def test_ingest_worker_terminal_copies_output_to_result_json(seeded_run):
    run_id, _, _ = seeded_run
    with Session(engine) as session:
        row = session.get(Run, run_id)
        assert row is not None
        row.status = "running"
        session.add(row)
        session.commit()

    await run_svc.ingest_worker_event(
        run_id,
        0,
        {
            "event": "run_completed",
            "node_id": None,
            "ts": "2026-08-30T00:00:00+00:00",
            "output": {"success": True, "summary": "ok", "steps_taken": 2},
        },
    )

    with Session(engine) as session:
        row = session.get(Run, run_id)
        assert row is not None
        assert row.status == "completed"
        assert row.finished_at is not None
        assert row.result_json is not None
        dumped = json.loads(row.result_json)
        assert dumped["success"] is True
        assert dumped["summary"] == "ok"
        assert dumped["steps_taken"] == 2
