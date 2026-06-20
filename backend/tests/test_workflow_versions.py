"""Manual workflow version save API tests."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def workflow_id(client: TestClient) -> str:
    name = f"version-test-{uuid.uuid4().hex[:8]}"
    resp = client.post("/api/workflows", json={"name": name})
    assert resp.status_code == 200, resp.text
    wf_id = resp.json()["id"]
    yield wf_id
    client.delete(f"/api/workflows/{wf_id}")


def test_create_workflow_then_post_manual_version_with_navigate(
    client: TestClient,
    workflow_id: str,
) -> None:
    workflow = {
        "nodes": [
            {"id": "start", "type": "start", "label": "Start", "params": {}},
            {
                "id": "nav1",
                "type": "navigate",
                "label": "Open site",
                "params": {"url": "https://example.com"},
            },
        ],
        "edges": [{"id": "e1", "source": "start", "target": "nav1"}],
        "start_id": "start",
        "parameters": [],
    }

    resp = client.post(
        f"/api/workflows/{workflow_id}/versions",
        json={"workflow": workflow, "authored_by": "manual"},
    )
    assert resp.status_code == 200, resp.text
    version = resp.json()
    assert version["workflow_id"] == workflow_id
    assert version["version_index"] == 2
    assert version["authored_by"] == "manual"
    assert len(version["workflow"]["nodes"]) == 2
    navigate = next(
        n for n in version["workflow"]["nodes"] if n["type"] == "navigate"
    )
    assert navigate["params"]["url"] == "https://example.com"

    wf_resp = client.get(f"/api/workflows/{workflow_id}")
    assert wf_resp.status_code == 200
    current = wf_resp.json()["current_version"]
    assert current is not None
    assert current["id"] == version["id"]
    assert current["version_index"] == 2


def test_post_version_missing_workflow_returns_404(client: TestClient) -> None:
    workflow = {
        "nodes": [
            {"id": "start", "type": "start", "label": "Start", "params": {}},
        ],
        "edges": [],
        "start_id": "start",
        "parameters": [],
    }
    resp = client.post(
        "/api/workflows/wf-does-not-exist/versions",
        json={"workflow": workflow},
    )
    assert resp.status_code == 404
