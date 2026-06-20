from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.models import Run, RunEvent, Workflow, WorkflowVersion
from app.db.session import get_session
from app.main import app


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    def _get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    yield TestClient(app), engine
    app.dependency_overrides.clear()


def _seed_workflow(session: Session) -> tuple[str, str]:
    wf = Workflow(
        name="wf",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(wf)
    session.commit()
    session.refresh(wf)
    ver = WorkflowVersion(
        workflow_id=wf.id,
        version_index=1,
        nodes_json="[]",
        edges_json="[]",
        start_id="s",
        authored_by="manual",
    )
    session.add(ver)
    session.commit()
    session.refresh(ver)
    return wf.id, ver.id


def test_last_output_shapes_empty_when_no_run(client):
    http, engine = client
    with Session(engine) as session:
        wf_id, _ = _seed_workflow(session)

    res = http.get(f"/api/workflows/{wf_id}/last-output-shapes")
    assert res.status_code == 200
    body = res.json()
    assert body["run_id"] is None
    assert body["shapes"] == {}


def test_last_output_shapes_from_completed_run(client):
    http, engine = client
    with Session(engine) as session:
        wf_id, ver_id = _seed_workflow(session)
        started = datetime.now(timezone.utc)
        run = Run(
            workflow_id=wf_id,
            workflow_version_id=ver_id,
            status="completed",
            started_at=started,
            finished_at=started,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        session.add(
            RunEvent(
                run_id=run.id,
                seq=1,
                event_type="node_completed",
                node_id="n1",
                payload_json=json.dumps({"output": {"price": 10}}),
            )
        )
        session.commit()
        run_id = run.id

    res = http.get(f"/api/workflows/{wf_id}/last-output-shapes")
    assert res.status_code == 200
    body = res.json()
    assert body["run_id"] == run_id
    assert body["shapes"] == {"n1": {"price": 10}}


def test_last_output_shapes_skips_failed_run(client):
    http, engine = client
    with Session(engine) as session:
        wf_id, ver_id = _seed_workflow(session)
        started = datetime.now(timezone.utc)
        session.add(
            Run(
                workflow_id=wf_id,
                workflow_version_id=ver_id,
                status="failed",
                started_at=started,
                finished_at=started,
            )
        )
        ok = Run(
            workflow_id=wf_id,
            workflow_version_id=ver_id,
            status="completed",
            started_at=started,
            finished_at=started,
        )
        session.add(ok)
        session.commit()
        session.refresh(ok)
        session.add(
            RunEvent(
                run_id=ok.id,
                seq=1,
                event_type="node_completed",
                node_id="n2",
                payload_json=json.dumps({"output": {"ok": True}}),
            )
        )
        session.commit()

    res = http.get(f"/api/workflows/{wf_id}/last-output-shapes")
    assert res.status_code == 200
    assert res.json()["shapes"] == {"n2": {"ok": True}}
