"""Contract drift test: SDK models vs served OpenAPI."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parent
_SDK_ROOT = _REPO_ROOT / "sdk" / "python"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
if str(_SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(_SDK_ROOT))

from app.main import app
from auto_agent_sdk.models import RunCreate, RunOut, RunTaskRequest, RunTaskResponse, WorkflowListItem


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _schema_props(schema: dict, name: str) -> set[str]:
    ref = schema["components"]["schemas"][name]
    return set(ref.get("properties", {}).keys())


def test_sdk_models_match_openapi(client: TestClient) -> None:
    openapi = client.get("/openapi.json").json()
    schemas = openapi["components"]["schemas"]

    assert set(RunTaskRequest.model_fields.keys()) == _schema_props(openapi, "RunTaskRequest")
    assert set(RunTaskResponse.model_fields.keys()) == _schema_props(openapi, "RunTaskResponse")
    assert set(RunCreate.model_fields.keys()) == _schema_props(openapi, "RunCreate")
    assert set(RunOut.model_fields.keys()) == _schema_props(openapi, "RunOut")
    assert set(WorkflowListItem.model_fields.keys()) == _schema_props(openapi, "WorkflowListItem")

    for path in (
        "/api/v1/run-task",
        "/api/v1/runs",
        "/api/v1/runs/{run_id}",
        "/api/v1/runs/{run_id}/cancel",
        "/api/v1/workflows",
        "/api/v1/workflows/{workflow_id}/run",
    ):
        assert path in openapi["paths"]

    assert "BearerAuth" in schemas or "BearerAuth" in openapi["components"]["securitySchemes"]
