from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.models import Run, RunEvent, Workflow, WorkflowVersion
from app.db.session import get_session
from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def db_client(tmp_path):
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


def test_preview_evaluates_expression(client: TestClient) -> None:
    res = client.post(
        "/api/expressions/preview",
        json={"expression": "2 + 3", "context": {}},
    )
    assert res.status_code == 200
    data = res.json()
    assert data == {
        "ok": True,
        "type": "int",
        "value": 5,
        "error": None,
    }


def test_preview_uses_context_namespace(client: TestClient) -> None:
    res = client.post(
        "/api/expressions/preview",
        json={
            "expression": "nodes.n1.output.price * 2",
            "context": {"nodes": {"n1": {"output": {"price": 10}}}},
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["type"] == "int"
    assert data["value"] == 20


def test_preview_strips_expression_token_wrapper(client: TestClient) -> None:
    res = client.post(
        "/api/expressions/preview",
        json={"expression": "{{= 1 + 1 }}", "context": {}},
    )
    assert res.status_code == 200
    assert res.json()["value"] == 2


def test_preview_returns_error_for_unsafe_expression(client: TestClient) -> None:
    res = client.post(
        "/api/expressions/preview",
        json={"expression": "__import__('os')", "context": {}},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is False
    assert data["value"] is None
    assert data["type"] is None
    assert isinstance(data["error"], str)
    assert "expression failed" in data["error"]


def test_preview_auto_loads_workflow_context(db_client) -> None:
    http, engine = db_client
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

    res = http.post(
        "/api/expressions/preview",
        json={
            "workflow_id": wf_id,
            "expression": "nodes.n1.output.price * 2",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data == {
        "ok": True,
        "type": "int",
        "value": 20,
        "error": None,
    }


def test_preview_workflow_without_run_data(db_client) -> None:
    http, engine = db_client
    with Session(engine) as session:
        wf_id, _ = _seed_workflow(session)

    res = http.post(
        "/api/expressions/preview",
        json={
            "workflow_id": wf_id,
            "expression": "nodes.n1.output.price * 2",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data == {
        "ok": False,
        "type": None,
        "value": None,
        "error": "no run data",
    }


def test_preview_prefers_explicit_context_over_workflow(db_client) -> None:
    http, engine = db_client
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
                payload_json=json.dumps({"output": {"price": 99}}),
            )
        )
        session.commit()

    res = http.post(
        "/api/expressions/preview",
        json={
            "workflow_id": wf_id,
            "expression": "nodes.n1.output.price * 2",
            "context": {"nodes": {"n1": {"output": {"price": 10}}}},
        },
    )
    assert res.status_code == 200
    assert res.json()["value"] == 20
