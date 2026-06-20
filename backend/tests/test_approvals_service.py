"""Unit tests for the approvals service."""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

import pytest
from sqlmodel import Session

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.models import Run, RunApproval, Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.services import approvals as approvals_svc


@pytest.fixture(autouse=True)
def _fresh_db():
    init_db()
    approvals_svc._events.clear()


def _seed_running_run(session: Session) -> tuple[str, str]:
    wf = Workflow(name=f"wf-{uuid.uuid4().hex[:8]}")
    session.add(wf)
    session.commit()
    session.refresh(wf)
    version = WorkflowVersion(
        workflow_id=wf.id,
        version_index=1,
        nodes_json="[]",
        edges_json="[]",
        start_id="start",
        authored_by="manual",
    )
    session.add(version)
    session.commit()
    session.refresh(version)
    run = Run(
        workflow_id=wf.id,
        workflow_version_id=version.id,
        status="running",
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run.id, wf.id


def test_request_inserts_pending_row():
    with Session(engine) as session:
        run_id, _ = _seed_running_run(session)
        row = approvals_svc.request(
            session,
            run_id=run_id,
            node_id="n1",
            prompt="ok?",
            inputs_schema=[{"name": "note", "type": "string", "required": True}],
        )
        assert row.decision is None
        assert row.seq == 1
        assert row.prompt == "ok?"
        assert row.id in approvals_svc._events


def test_resolve_approve_sets_row_and_fires_event():
    with Session(engine) as session:
        run_id, _ = _seed_running_run(session)
        row = approvals_svc.request(
            session,
            run_id=run_id,
            node_id="n1",
            prompt="ok?",
            inputs_schema=[{"name": "note", "type": "string", "required": True}],
        )
        event = approvals_svc._events[row.id]
        resolved = approvals_svc.resolve(
            session, row.id, "approve", {"note": "hello"}
        )
        assert resolved.decision == "approve"
        assert resolved.decision_inputs == {"note": "hello"}
        assert resolved.resolved_at is not None
        assert event.is_set()


def test_resolve_reject():
    with Session(engine) as session:
        run_id, _ = _seed_running_run(session)
        row = approvals_svc.request(
            session,
            run_id=run_id,
            node_id="n1",
            prompt="ok?",
            inputs_schema=[],
        )
        resolved = approvals_svc.resolve(session, row.id, "reject", {})
        assert resolved.decision == "reject"


@pytest.mark.asyncio
async def test_wait_blocks_until_resolve():
    with Session(engine) as session:
        run_id, _ = _seed_running_run(session)
        row = approvals_svc.request(
            session,
            run_id=run_id,
            node_id="n1",
            prompt="ok?",
            inputs_schema=[],
        )

        async def resolve_later():
            await asyncio.sleep(0.05)
            with Session(engine) as s2:
                approvals_svc.resolve(s2, row.id, "approve", {})

        task = asyncio.create_task(resolve_later())
        resolved = await approvals_svc.wait(row.id)
        await task
        assert resolved.decision == "approve"


def test_duplicate_resolve_raises():
    with Session(engine) as session:
        run_id, _ = _seed_running_run(session)
        row = approvals_svc.request(
            session,
            run_id=run_id,
            node_id="n1",
            prompt="ok?",
            inputs_schema=[],
        )
        approvals_svc.resolve(session, row.id, "approve", {})
        with pytest.raises(approvals_svc.ApprovalAlreadyResolved):
            approvals_svc.resolve(session, row.id, "approve", {})


def test_pending_for_run_returns_latest_unresolved():
    with Session(engine) as session:
        run_id, _ = _seed_running_run(session)
        approvals_svc.request(
            session,
            run_id=run_id,
            node_id="n1",
            prompt="first",
            inputs_schema=[],
        )
        row2 = approvals_svc.request(
            session,
            run_id=run_id,
            node_id="n2",
            prompt="second",
            inputs_schema=[],
        )
        pending = approvals_svc.pending_for_run(session, run_id)
        assert pending is not None
        assert pending.id == row2.id


def test_validate_inputs_rejects_missing_required():
    with Session(engine) as session:
        run_id, _ = _seed_running_run(session)
        row = approvals_svc.request(
            session,
            run_id=run_id,
            node_id="n1",
            prompt="ok?",
            inputs_schema=[{"name": "note", "type": "string", "required": True}],
        )
        with pytest.raises(approvals_svc.ApprovalInputValidationError) as exc:
            approvals_svc.resolve(session, row.id, "approve", {})
        assert "note" in exc.value.errors
