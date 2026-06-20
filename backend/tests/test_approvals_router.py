"""Integration tests for approval REST endpoints and executor pause/resume."""
from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app import executor
from app.db.models import Run, Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.main import app
from app.schemas import Edge, Node, Workflow as WorkflowSchema
from app.services import approvals as approvals_svc
from app.services import runs as run_svc


def _approval_workflow() -> WorkflowSchema:
    return WorkflowSchema(
        nodes=[
            Node(id="start", type="start", label="start"),
            Node(
                id="approve",
                type="approval",
                label="confirm",
                params={
                    "prompt": "确认继续？",
                    "inputs": [{"name": "note", "type": "string", "required": True}],
                },
            ),
            Node(id="end", type="end", label="end"),
        ],
        edges=[
            Edge(id="e1", source="start", target="approve"),
            Edge(id="e2", source="approve", target="end"),
        ],
        start_id="start",
    )


@pytest.fixture(autouse=True)
def _fresh_db():
    init_db()
    approvals_svc._events.clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def workflow_id() -> str:
    with Session(engine) as session:
        wf = Workflow(name=f"approval-wf-{uuid.uuid4().hex[:8]}")
        session.add(wf)
        session.commit()
        session.refresh(wf)
        wf_json = _approval_workflow().model_dump()
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


async def _noop_begin(*_a, **_k):
    return None


async def _noop_end(*_a, **_k):
    return None


async def _noop_trace_start(*_a, **_k):
    return None


async def _noop_trace_stop(*_a, **_k):
    return None


async def _noop_livestream(*_a, **_k):
    return None


def _patch_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.tools.browser.begin_run", _noop_begin)
    monkeypatch.setattr("app.tools.browser.end_run", _noop_end)
    monkeypatch.setattr("app.tools.browser.start_run_trace", _noop_trace_start)
    monkeypatch.setattr("app.tools.browser.stop_run_trace", _noop_trace_stop)
    monkeypatch.setattr("app.services.livestream.on_run_ended", _noop_livestream)


def _enqueue_run(workflow_id: str) -> str:
    with Session(engine) as session:
        run = run_svc.enqueue_run(workflow_id, session)
        run_id = run.id
    run_svc.remove_from_queue_for_tests(run_id)
    return run_id


async def _wait_for_event_async(
    run_id: str, event_name: str, timeout: float = 5.0
) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        events = run_svc.fetch_prior_events(run_id)
        for ev in events:
            if ev.get("event") == event_name:
                return ev
        await asyncio.sleep(0.05)
    raise TimeoutError(f"event {event_name!r} not seen for run {run_id}")


async def _run_until_approval(workflow_id: str) -> tuple[str, asyncio.Task]:
    run_id = _enqueue_run(workflow_id)
    drive_task = asyncio.create_task(run_svc._drive_run(run_id))
    await _wait_for_event_async(run_id, "node_awaiting_approval")
    return run_id, drive_task


@pytest.mark.asyncio
async def test_executor_approve_resumes(
    monkeypatch: pytest.MonkeyPatch, workflow_id: str
) -> None:
    _patch_browser(monkeypatch)
    run_id, drive_task = await _run_until_approval(workflow_id)

    with Session(engine) as session:
        pending = approvals_svc.pending_for_run(session, run_id)
        assert pending is not None
        assert pending.node_id == "approve"

    with Session(engine) as session:
        approvals_svc.resolve(
            session, pending.id, "approve", {"note": "ok"}  # type: ignore[union-attr]
        )

    await drive_task
    await _wait_for_event_async(run_id, "node_approved")
    await _wait_for_event_async(run_id, "run_completed")

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "completed"
        completed = [
            e
            for e in run_svc.fetch_prior_events(run_id)
            if e.get("event") == "node_completed" and e.get("node_id") == "approve"
        ]
        assert completed
        assert completed[0]["output"]["inputs"]["note"] == "ok"


@pytest.mark.asyncio
async def test_executor_reject_terminates_as_rejected(
    monkeypatch: pytest.MonkeyPatch, workflow_id: str
) -> None:
    _patch_browser(monkeypatch)
    run_id, drive_task = await _run_until_approval(workflow_id)

    with Session(engine) as session:
        pending = approvals_svc.pending_for_run(session, run_id)
        assert pending is not None
        approvals_svc.resolve(session, pending.id, "reject", {})

    await drive_task
    await _wait_for_event_async(run_id, "run_rejected")

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "rejected"


@pytest.mark.asyncio
async def test_router_approve_happy_path(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    workflow_id: str,
) -> None:
    _patch_browser(monkeypatch)
    run_id, drive_task = await _run_until_approval(workflow_id)

    detail = client.get(f"/api/runs/{run_id}")
    assert detail.status_code == 200
    pending = detail.json()["run"]["pending_approval"]
    assert pending is not None
    assert pending["node_id"] == "approve"

    listed = client.get(f"/api/runs/{run_id}/approvals")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    resolve = client.post(
        f"/api/runs/{run_id}/approvals/approve",
        json={"decision": "approve", "inputs": {"note": "ok"}},
    )
    assert resolve.status_code == 200
    body = resolve.json()
    assert body["decision"] == "approve"
    assert body["inputs"]["note"] == "ok"

    await drive_task
    await _wait_for_event_async(run_id, "run_completed")
    detail2 = client.get(f"/api/runs/{run_id}")
    assert detail2.json()["run"]["pending_approval"] is None


@pytest.mark.asyncio
async def test_router_duplicate_resolve_returns_409(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    workflow_id: str,
) -> None:
    _patch_browser(monkeypatch)
    run_id, drive_task = await _run_until_approval(workflow_id)

    first = client.post(
        f"/api/runs/{run_id}/approvals/approve",
        json={"decision": "approve", "inputs": {"note": "ok"}},
    )
    assert first.status_code == 200
    second = client.post(
        f"/api/runs/{run_id}/approvals/approve",
        json={"decision": "approve", "inputs": {"note": "ok"}},
    )
    assert second.status_code == 409
    await drive_task


@pytest.mark.asyncio
async def test_router_invalid_inputs_returns_422(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    workflow_id: str,
) -> None:
    _patch_browser(monkeypatch)
    run_id, drive_task = await _run_until_approval(workflow_id)

    bad = client.post(
        f"/api/runs/{run_id}/approvals/approve",
        json={"decision": "approve", "inputs": {}},
    )
    assert bad.status_code == 422

    with Session(engine) as session:
        pending = approvals_svc.pending_for_run(session, run_id)
        assert pending is not None
        assert pending.decision is None

    good = client.post(
        f"/api/runs/{run_id}/approvals/approve",
        json={"decision": "approve", "inputs": {"note": "fixed"}},
    )
    assert good.status_code == 200
    await drive_task


def test_router_non_running_returns_410(
    client: TestClient, workflow_id: str
) -> None:
    with Session(engine) as session:
        wf = session.get(Workflow, workflow_id)
        version_id = wf.current_version_id  # type: ignore[union-attr]
        run = Run(
            workflow_id=workflow_id,
            workflow_version_id=version_id,
            status="completed",
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        approvals_svc.request(
            session,
            run_id=run.id,
            node_id="approve",
            prompt="x",
            inputs_schema=[],
        )
        run_id = run.id

    resp = client.post(
        f"/api/runs/{run_id}/approvals/approve",
        json={"decision": "approve", "inputs": {}},
    )
    assert resp.status_code == 410


@pytest.mark.asyncio
async def test_abort_during_approval_marks_lost_and_returns_410(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    workflow_id: str,
) -> None:
    _patch_browser(monkeypatch)
    run_id, drive_task = await _run_until_approval(workflow_id)

    abort = client.post(f"/api/runs/{run_id}/abort")
    assert abort.status_code == 200
    await drive_task
    await _wait_for_event_async(run_id, "run_aborted")

    post = client.post(
        f"/api/runs/{run_id}/approvals/approve",
        json={"decision": "approve", "inputs": {"note": "late"}},
    )
    assert post.status_code == 410

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "aborted"
        pending = approvals_svc.pending_for_run(session, run_id)
        assert pending is None


def test_direct_executor_approval_events() -> None:
    wf = _approval_workflow()
    events: list[dict] = []

    async def on_event(payload: dict) -> None:
        events.append(payload)

    async def run_flow() -> None:
        with Session(engine) as session:
            wf_row = Workflow(name=f"wf-{uuid.uuid4().hex[:8]}")
            session.add(wf_row)
            session.commit()
            session.refresh(wf_row)
            version = WorkflowVersion(
                workflow_id=wf_row.id,
                version_index=1,
                nodes_json=json.dumps(wf.model_dump()["nodes"]),
                edges_json=json.dumps(wf.model_dump()["edges"]),
                start_id=wf.start_id,
                authored_by="manual",
            )
            session.add(version)
            session.commit()
            session.refresh(version)
            run = Run(
                workflow_id=wf_row.id,
                workflow_version_id=version.id,
                status="running",
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            run_id = run.id

            async def resolve_after_wait() -> None:
                await asyncio.sleep(0.05)
                with Session(engine) as s2:
                    pending = approvals_svc.pending_for_run(s2, run_id)
                    assert pending is not None
                    approvals_svc.resolve(
                        s2, pending.id, "approve", {"note": "direct"}
                    )

            await asyncio.gather(
                resolve_after_wait(),
                executor.run_workflow(
                    wf,
                    on_event,
                    session=session,
                    run_id=run_id,
                ),
            )

    asyncio.run(run_flow())

    names = [e["event"] for e in events]
    assert "node_awaiting_approval" in names
    assert "node_approved" in names
    assert "node_completed" in names
    assert events[-1]["event"] == "run_completed"
