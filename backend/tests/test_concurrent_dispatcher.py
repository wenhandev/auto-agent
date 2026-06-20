"""Tests for the global concurrent run dispatcher."""

from __future__ import annotations

import asyncio
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

from app.db.models import Run, Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.schemas import Edge, Node, Workflow as WorkflowSchema
from app.services import browser_pool
from app.services import runs as run_svc
from app.settings import settings


def _minimal_workflow() -> WorkflowSchema:
    return WorkflowSchema(
        nodes=[
            Node(id="start", type="start", label="start"),
            Node(id="end", type="end", label="end"),
        ],
        edges=[Edge(id="e1", source="start", target="end")],
        start_id="start",
    )


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch):
    init_db()
    run_svc.reset_dispatcher_for_tests()
    browser_pool.reset_for_tests()
    monkeypatch.setattr(settings, "max_concurrent_browser_runs", 3)
    monkeypatch.setattr(settings, "max_queue_depth", 5)
    monkeypatch.setattr(settings, "allow_parallel_per_workflow", False)
    monkeypatch.setattr("app.tools.browser.begin_run", AsyncMock())
    monkeypatch.setattr("app.tools.browser.end_run", AsyncMock())
    monkeypatch.setattr("app.tools.browser.start_run_trace", AsyncMock())
    monkeypatch.setattr("app.tools.browser.stop_run_trace", AsyncMock())
    monkeypatch.setattr("app.services.livestream.on_run_ended", AsyncMock())
    yield
    run_svc.reset_dispatcher_for_tests()
    browser_pool.reset_for_tests()


def _seed_workflow(name: str | None = None) -> str:
    wf_json = _minimal_workflow().model_dump()
    with Session(engine) as session:
        wf = Workflow(name=name or f"wf-{uuid.uuid4().hex[:8]}")
        session.add(wf)
        session.commit()
        session.refresh(wf)
        version = WorkflowVersion(
            workflow_id=wf.id,
            version_index=1,
            nodes_json=json.dumps(wf_json["nodes"]),
            edges_json=json.dumps(wf_json["edges"]),
            start_id=wf_json["start_id"],
            authored_by="manual",
        )
        session.add(version)
        session.commit()
        session.refresh(version)
        wf.current_version_id = version.id
        session.add(wf)
        session.commit()
        return wf.id


async def _enqueue_async(wf_id: str) -> str:
    with Session(engine) as session:
        run = run_svc.enqueue_run(wf_id, session)
        run_id = run.id
    await run_svc._ensure_dispatcher()
    await asyncio.sleep(0.05)
    return run_id


@pytest.mark.asyncio
async def test_admits_up_to_max_concurrent(monkeypatch: pytest.MonkeyPatch) -> None:
    hold = asyncio.Event()
    original = run_svc._drive_run

    async def blocking_drive(run_id: str) -> None:
        with Session(engine) as session:
            run = session.get(Run, run_id)
            if run is not None and run.status == "queued":
                run.status = "running"
                session.add(run)
                session.commit()
        await hold.wait()

    monkeypatch.setattr(run_svc, "_drive_run", blocking_drive)
    wf_ids = [_seed_workflow() for _ in range(5)]
    ids = [await _enqueue_async(wf) for wf in wf_ids]
    stats = run_svc.dispatcher_stats()
    assert stats["running"] == 3
    assert stats["queued"] == 2
    assert run_svc.queue_position(ids[3]) == 1
    assert run_svc.queue_position(ids[4]) == 2
    hold.set()


@pytest.mark.asyncio
async def test_same_workflow_serialises(monkeypatch: pytest.MonkeyPatch) -> None:
    hold = asyncio.Event()
    original = run_svc._drive_run

    async def blocking_drive(run_id: str) -> None:
        with Session(engine) as session:
            run = session.get(Run, run_id)
            if run is not None and run.status == "queued":
                run.status = "running"
                session.add(run)
                session.commit()
        await hold.wait()

    monkeypatch.setattr(run_svc, "_drive_run", blocking_drive)
    wf = _seed_workflow()
    r1 = await _enqueue_async(wf)
    r2 = await _enqueue_async(wf)
    assert len(run_svc._running) == 1
    assert run_svc.queue_position(r2) == 1
    hold.set()


@pytest.mark.asyncio
async def test_round_robin_across_workflows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "max_concurrent_browser_runs", 2)
    hold = asyncio.Event()
    started: list[str] = []

    async def blocking_drive(run_id: str) -> None:
        wf_id = run_svc._run_workflow.get(run_id)
        started.append(wf_id or "")
        with Session(engine) as session:
            run = session.get(Run, run_id)
            if run is not None and run.status == "queued":
                run.status = "running"
                session.add(run)
                session.commit()
        if len(started) == 1:
            await hold.wait()

    monkeypatch.setattr(run_svc, "_drive_run", blocking_drive)
    wf_a = _seed_workflow("wf-a")
    wf_b = _seed_workflow("wf-b")
    await _enqueue_async(wf_a)
    await _enqueue_async(wf_b)
    await asyncio.sleep(0.15)
    assert len(started) == 2
    assert started[0] != started[1]
    hold.set()


def test_queue_full_returns_429(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr(settings, "max_queue_depth", 2)
    run_svc.reset_dispatcher_for_tests()
    wf = _seed_workflow()
    with Session(engine) as session:
        run_svc.enqueue_run(wf, session)
        run_svc.enqueue_run(wf, session)
        with pytest.raises(run_svc.QueueFullError):
            run_svc.enqueue_run(wf, session)

    client = TestClient(app)
    run_svc.reset_dispatcher_for_tests()
    wf2 = _seed_workflow()
    with Session(engine) as session:
        run_svc.enqueue_run(wf2, session)
        run_svc.enqueue_run(wf2, session)
    resp = client.post(f"/api/workflows/{wf2}/runs", json={})
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_approval_pause_releases_dispatch_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hold = asyncio.Event()
    monkeypatch.setattr(settings, "max_concurrent_browser_runs", 1)

    async def blocking_drive(run_id: str) -> None:
        with Session(engine) as session:
            run = session.get(Run, run_id)
            if run is not None and run.status == "queued":
                run.status = "running"
                session.add(run)
                session.commit()
        await hold.wait()

    monkeypatch.setattr(run_svc, "_drive_run", blocking_drive)
    wf_a = _seed_workflow("wf-a")
    wf_b = _seed_workflow("wf-b")
    await _enqueue_async(wf_a)
    assert len(run_svc._running) == 1
    run_svc._approval_paused.add(next(iter(run_svc._running)))
    run_svc._release_slot(next(iter(run_svc._running)))
    await _enqueue_async(wf_b)
    await asyncio.sleep(0.1)
    assert len(run_svc._running) == 1
    hold.set()


@pytest.mark.asyncio
async def test_max_concurrent_one_serialises_globally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "max_concurrent_browser_runs", 1)
    hold = asyncio.Event()

    async def blocking_drive(run_id: str) -> None:
        with Session(engine) as session:
            run = session.get(Run, run_id)
            if run is not None and run.status == "queued":
                run.status = "running"
                session.add(run)
                session.commit()
        await hold.wait()

    monkeypatch.setattr(run_svc, "_drive_run", blocking_drive)
    wf = _seed_workflow()
    await _enqueue_async(wf)
    await _enqueue_async(wf)
    assert run_svc.dispatcher_stats()["running"] == 1
    hold.set()


def test_schedule_skips_coroutine_without_loop() -> None:
    """_schedule must not instantiate coroutines when no event loop is registered."""
    import warnings

    calls: list[str] = []

    async def _marker() -> None:
        calls.append("ran")

    run_svc.set_main_loop(None)  # type: ignore[arg-type]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        run_svc._schedule(_marker)
    assert calls == []
    assert not any("coroutine" in str(w.message) for w in caught)
