"""Workflow input parameter validation, API, and trigger mapping tests."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.models import Run, Trigger, Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.main import app
from app.schemas import Workflow as WorkflowSchema
from app.services import workflow_parameters as param_svc
from app.services import workflows as workflow_svc


def _param_workflow_json(**extra_params: object) -> dict:
    parameters = [
        {
            "name": "search_term",
            "type": "string",
            "required": True,
        },
        {
            "name": "limit",
            "type": "number",
            "required": False,
            "default": 10,
        },
        {
            "name": "verbose",
            "type": "boolean",
            "required": False,
            "default": False,
        },
        {
            "name": "api_key",
            "type": "secret",
            "required": False,
        },
        {
            "name": "filters",
            "type": "json",
            "required": False,
            "default": {"active": True},
        },
    ]
    return {
        "nodes": [
            {"id": "start", "type": "start", "label": "开始", "params": {}},
        ],
        "edges": [],
        "start_id": "start",
        "parameters": parameters,
    }


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def workflow_with_params() -> str:
    init_db()
    with Session(engine) as session:
        wf_json = _param_workflow_json()
        WorkflowSchema.model_validate(wf_json)
        wf = Workflow(name=f"params-wf-{uuid.uuid4().hex[:8]}")
        session.add(wf)
        session.commit()
        session.refresh(wf)
        version = WorkflowVersion(
            workflow_id=wf.id,
            version_index=1,
            nodes_json=json.dumps(wf_json["nodes"]),
            edges_json=json.dumps(wf_json["edges"]),
            start_id=wf_json["start_id"],
            parameters_json=json.dumps(wf_json["parameters"]),
            authored_by="manual",
        )
        session.add(version)
        session.commit()
        session.refresh(version)
        wf.current_version_id = version.id
        session.add(wf)
        session.commit()
        return wf.id


def test_validate_required_missing():
    declared = WorkflowSchema.model_validate(_param_workflow_json()).parameters
    with pytest.raises(param_svc.ParameterValidationError) as ei:
        param_svc.validate_and_resolve_parameters(declared, {})
    assert "search_term" in str(ei.value)


def test_validate_default_applied():
    declared = WorkflowSchema.model_validate(_param_workflow_json()).parameters
    resolved = param_svc.validate_and_resolve_parameters(
        declared, {"search_term": "shoes"}
    )
    assert resolved["search_term"] == "shoes"
    assert resolved["limit"] == 10
    assert resolved["verbose"] is False
    assert resolved["filters"] == {"active": True}


def test_validate_type_mismatch():
    declared = WorkflowSchema.model_validate(_param_workflow_json()).parameters
    with pytest.raises(param_svc.ParameterValidationError) as ei:
        param_svc.validate_and_resolve_parameters(
            declared, {"search_term": "shoes", "limit": "not-a-number"}
        )
    assert "limit" in str(ei.value)


def test_mask_secret_parameter():
    declared = WorkflowSchema.model_validate(_param_workflow_json()).parameters
    masked = param_svc.mask_parameters(
        {"api_key": "supersecret99", "search_term": "shoes"},
        declared,
    )
    assert masked["api_key"] == "***99"
    assert masked["search_term"] == "shoes"
    assert "supersecret" not in masked["api_key"]


def test_split_trigger_body():
    declared = WorkflowSchema.model_validate(_param_workflow_json()).parameters
    mapped, passthrough = param_svc.split_trigger_body(
        declared,
        {
            "search_term": "boots",
            "limit": 5,
            "extra_field": "keep-me",
        },
    )
    assert mapped == {"search_term": "boots", "limit": 5}
    assert passthrough == {"extra_field": "keep-me"}


def test_create_run_with_parameters(client: TestClient, workflow_with_params: str) -> None:
    resp = client.post(
        f"/api/workflows/{workflow_with_params}/runs",
        json={"parameters": {"search_term": "shoes", "limit": 3}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["parameters"]["search_term"] == "shoes"
    assert body["parameters"]["limit"] == 3


def test_create_run_missing_required(client: TestClient, workflow_with_params: str) -> None:
    resp = client.post(
        f"/api/workflows/{workflow_with_params}/runs",
        json={"parameters": {"limit": 3}},
    )
    assert resp.status_code == 422
    assert "search_term" in resp.json()["detail"]


def test_create_run_secret_masked_in_response(
    client: TestClient, workflow_with_params: str
) -> None:
    resp = client.post(
        f"/api/workflows/{workflow_with_params}/runs",
        json={
            "parameters": {
                "search_term": "shoes",
                "api_key": "topsecret42",
            }
        },
    )
    assert resp.status_code == 200
    params = resp.json()["parameters"]
    assert params["api_key"] == "***42"
    assert "topsecret" not in params["api_key"]


def test_post_api_runs_accepts_parameters(
    client: TestClient, workflow_with_params: str
) -> None:
    resp = client.post(
        "/api/runs",
        json={
            "workflow_id": workflow_with_params,
            "parameters": {"search_term": "hats"},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["parameters"]["search_term"] == "hats"


def test_workflow_without_parameters_unchanged(client: TestClient) -> None:
    init_db()
    with Session(engine) as session:
        wf = workflow_svc.create_workflow(
            name=f"plain-wf-{uuid.uuid4().hex[:8]}",
            session=session,
        )
        wf_id = wf.id
    resp = client.post(f"/api/workflows/{wf_id}/runs", json={})
    assert resp.status_code == 200
    assert resp.json().get("parameters") in (None, {})


def test_reserved_parameter_name_rejected():
    with pytest.raises(ValueError, match="shadows a reserved namespace"):
        WorkflowSchema.model_validate(
            {
                "nodes": [{"id": "s", "type": "start", "label": "x", "params": {}}],
                "edges": [],
                "start_id": "s",
                "parameters": [{"name": "nodes", "type": "string"}],
            }
        )


def test_persist_resolved_parameters_on_run(
    client: TestClient, workflow_with_params: str
) -> None:
    resp = client.post(
        f"/api/workflows/{workflow_with_params}/runs",
        json={"parameters": {"search_term": "bags", "verbose": True}},
    )
    run_id = resp.json()["id"]
    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        stored = json.loads(run.parameters_json or "{}")
        assert stored["search_term"] == "bags"
        assert stored["verbose"] is True
