"""Run input file staging, materialization, and API tests."""

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

from app.db.models import Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.main import app
from app.schemas import Workflow as WorkflowSchema
from app.services import run_inputs as run_input_svc
from app.services import workflow_parameters as param_svc


@pytest.fixture()
def input_tmp(tmp_path: Path):
    staging = tmp_path / "staging"
    run_inputs = tmp_path / "run_inputs"
    workflow_files = tmp_path / "workflow_files"
    run_input_svc.set_staging_root(staging)
    run_input_svc.set_run_inputs_root(run_inputs)
    from app.tools import sandbox as sandbox_mod

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(sandbox_mod, "WORKSPACE_DIR", workflow_files)
    yield staging, run_inputs, workflow_files
    run_input_svc.reset_roots()
    monkeypatch.undo()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def workflow_with_file_param() -> str:
    init_db()
    parameters = [
        {"name": "csv_file", "type": "file", "required": True},
        {"name": "search_term", "type": "string", "required": True},
    ]
    wf_json = {
        "nodes": [{"id": "start", "type": "start", "label": "start", "params": {}}],
        "edges": [],
        "start_id": "start",
        "parameters": parameters,
    }
    WorkflowSchema.model_validate(wf_json)
    with Session(engine) as session:
        wf = Workflow(name=f"file-wf-{uuid.uuid4().hex[:8]}")
        session.add(wf)
        session.commit()
        session.refresh(wf)
        version = WorkflowVersion(
            workflow_id=wf.id,
            version_index=1,
            nodes_json=json.dumps(wf_json["nodes"]),
            edges_json=json.dumps(wf_json["edges"]),
            start_id=wf_json["start_id"],
            parameters_json=json.dumps(parameters),
            authored_by="manual",
        )
        session.add(version)
        session.commit()
        session.refresh(version)
        wf.current_version_id = version.id
        session.add(wf)
        session.commit()
        return wf.id


def test_staging_and_materialize(
    input_tmp,
    workflow_with_file_param: str,
) -> None:
    wf_id = workflow_with_file_param
    declared = WorkflowSchema.model_validate(
        {
            "nodes": [{"id": "start", "type": "start", "label": "s", "params": {}}],
            "edges": [],
            "start_id": "start",
            "parameters": [
                {"name": "csv_file", "type": "file", "required": True},
            ],
        }
    ).parameters

    meta = run_input_svc.store_staging_file(
        wf_id,
        b"col1,col2\n1,2\n",
        filename="data.csv",
        content_type="text/csv",
    )
    resolved = param_svc.validate_and_resolve_parameters(
        declared,
        {"csv_file": {"file_id": meta["file_id"]}},
    )
    run_id = str(uuid.uuid4())
    materialized = run_input_svc.materialize_file_parameters(
        wf_id,
        run_id,
        resolved,
        declared,
    )

    assert materialized["csv_file"]["path"].startswith("inputs/")
    assert materialized["csv_file"]["filename"] == "data.csv"
    run_copy = run_input_svc.resolve_run_input_file(run_id, meta["file_id"])
    assert run_copy is not None
    assert run_copy.read_bytes() == b"col1,col2\n1,2\n"

    from app.tools.sandbox import resolve_sandbox_path

    sandbox_path = resolve_sandbox_path(
        materialized["csv_file"]["path"],
        workflow_id=wf_id,
    )
    assert sandbox_path.is_file()
    assert sandbox_path.read_bytes() == b"col1,col2\n1,2\n"


def test_upload_and_create_run_with_file_param(
    input_tmp,
    client: TestClient,
    workflow_with_file_param: str,
) -> None:
    wf_id = workflow_with_file_param
    upload = client.post(
        f"/api/workflows/{wf_id}/input-files",
        files={"file": ("report.csv", b"a,b,c", "text/csv")},
    )
    assert upload.status_code == 200, upload.text
    file_id = upload.json()["file_id"]

    create = client.post(
        f"/api/workflows/{wf_id}/runs",
        json={
            "parameters": {
                "search_term": "test",
                "csv_file": {"file_id": file_id},
            }
        },
    )
    assert create.status_code == 200, create.text
    run = create.json()
    assert run["parameters"]["csv_file"]["filename"] == "report.csv"
    assert "file_id" not in run["parameters"]["csv_file"]

    listed = client.get(f"/api/runs/{run['id']}/input-files")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    download = client.get(
        f"/api/runs/{run['id']}/input-files/{file_id}",
    )
    assert download.status_code == 200
    assert download.content == b"a,b,c"


def test_file_param_validation() -> None:
    declared = WorkflowSchema.model_validate(
        {
            "nodes": [{"id": "start", "type": "start", "label": "s", "params": {}}],
            "edges": [],
            "start_id": "start",
            "parameters": [{"name": "doc", "type": "file", "required": True}],
        }
    ).parameters
    with pytest.raises(param_svc.ParameterValidationError):
        param_svc.validate_and_resolve_parameters(declared, {"doc": 123})
