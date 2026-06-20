"""Regression tests for list endpoints accepting all terminal run statuses."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlmodel import Session

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.models import Run, Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.routers.runs import _list_item
from app.routers.workflows import list_workflows_impl
from app.schemas_api import RunListItem, RunStatus, WorkflowListItem
from app.services.orgs import get_default_org_id


@pytest.fixture()
def workflow_with_runs() -> tuple[str, str]:
    init_db()
    with Session(engine) as session:
        wf = Workflow(name="status-list-wf")
        session.add(wf)
        session.commit()
        session.refresh(wf)
        version = WorkflowVersion(
            workflow_id=wf.id,
            version_index=1,
            nodes_json="[]",
            edges_json="[]",
            start_id="s",
            authored_by="manual",
        )
        session.add(version)
        session.commit()
        session.refresh(version)
        wf.current_version_id = version.id
        session.add(wf)
        session.commit()
        return wf.id, version.id


@pytest.mark.parametrize("status", ["rejected", "completed_with_errors"])
def test_workflow_list_item_accepts_terminal_statuses(status: RunStatus) -> None:
    item = WorkflowListItem(
        id="wf-1",
        name="demo",
        description=None,
        current_version_index=1,
        last_run_status=status,
        updated_at="2026-06-15T00:00:00Z",
    )
    assert item.last_run_status == status


@pytest.mark.parametrize("status", ["rejected", "completed_with_errors"])
def test_run_list_item_accepts_terminal_statuses(status: RunStatus) -> None:
    item = RunListItem(
        id="run-1",
        workflow_id="wf-1",
        workflow_name="demo",
        workflow_version_id="ver-1",
        version_index=1,
        status=status,
        queued_at="2026-06-15T00:00:00Z",
        started_at=None,
        finished_at="2026-06-15T00:01:00Z",
        duration_ms=60_000,
        error_summary=None,
    )
    assert item.status == status


def test_list_workflows_with_rejected_run(
    workflow_with_runs: tuple[str, str],
) -> None:
    wf_id, version_id = workflow_with_runs
    with Session(engine) as session:
        session.add(
            Run(
                workflow_id=wf_id,
                workflow_version_id=version_id,
                status="rejected",
            )
        )
        session.commit()
        org_id = get_default_org_id(session)
        items = list_workflows_impl(session, org_id, role="admin")

    row = next(item for item in items if item.id == wf_id)
    assert row.last_run_status == "rejected"


def test_list_runs_with_rejected_status(
    workflow_with_runs: tuple[str, str],
) -> None:
    wf_id, version_id = workflow_with_runs
    with Session(engine) as session:
        run = Run(
            workflow_id=wf_id,
            workflow_version_id=version_id,
            status="rejected",
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        wf = session.get(Workflow, wf_id)
        version = session.get(WorkflowVersion, version_id)
        assert wf is not None
        assert version is not None
        item = _list_item(run, wf.name, version.version_index)

    assert item.status == "rejected"
