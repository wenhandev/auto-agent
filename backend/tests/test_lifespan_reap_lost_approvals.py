"""Startup reaper for approvals lost across backend restart."""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest
from sqlmodel import Session, select

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.models import Run, RunApproval, RunEvent, Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.services import approvals as approvals_svc


@pytest.fixture(autouse=True)
def _fresh_db():
    init_db()
    approvals_svc._events.clear()


def _seed_pending(session: Session) -> tuple[str, str]:
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
    approval = RunApproval(
        run_id=run.id,
        node_id="n_approve",
        seq=1,
        prompt="confirm?",
        inputs_schema=[],
    )
    session.add(approval)
    session.commit()
    session.refresh(approval)
    return run.id, approval.id


def test_reap_lost_approvals_on_startup():
    with Session(engine) as session:
        run_id, approval_id = _seed_pending(session)

    count = approvals_svc.reap_lost_approvals_on_startup()
    assert count >= 1

    with Session(engine) as session:
        approval = session.get(RunApproval, approval_id)
        assert approval is not None
        assert approval.decision == "lost"
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "failed"
        assert run.error == "approval lost across backend restart"
        events = session.exec(
            select(RunEvent).where(RunEvent.run_id == run_id)
        ).all()
        assert len(events) == 1
        payload = json.loads(events[0].payload_json)
        assert payload["event"] == "run_failed"
        assert payload["reason"] == "approval lost across backend restart"
        assert payload["approval_id"] == approval_id
