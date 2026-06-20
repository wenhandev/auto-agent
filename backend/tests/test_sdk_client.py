"""Tests for the auto-agent Python SDK (httpx mock transport)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SDK_ROOT = _REPO_ROOT / "sdk" / "python"
if str(_SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(_SDK_ROOT))

from auto_agent_sdk import AutoAgent, AsyncAutoAgent, Client, AsyncClient
from auto_agent_sdk._http import ApiError


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_out(run_id: str = "run-1", status: str = "queued") -> dict:
    return {
        "id": run_id,
        "workflow_id": "wf-1",
        "workflow_version_id": "wv-1",
        "status": status,
        "mode": "graph",
        "queued_at": _utcnow(),
        "started_at": None,
        "finished_at": None,
        "error": None,
        "source": "api",
        "trigger_id": None,
        "trigger_context": {"kind": "api"},
        "parameters": None,
        "artifact_counts": {},
        "browser_profile_id": None,
        "totp_identifier": None,
        "pending_approval": None,
        "queue_position": 1,
    }


def _replay(run_id: str = "run-1", status: str = "queued") -> dict:
    return {
        "run": _run_out(run_id, status),
        "workflow_version": {
            "id": "wv-1",
            "workflow_id": "wf-1",
            "version_index": 1,
            "authored_by": "manual",
            "workflow": {"nodes": [], "edges": [], "start_id": "start", "parameters": []},
            "created_at": _utcnow(),
        },
        "events": [],
    }


def _mock_transport() -> httpx.MockTransport:
    calls: list[tuple[str, str, bytes | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content or None
        calls.append((request.method, str(request.url), body))
        auth = request.headers.get("Authorization")
        if auth != "Bearer sk_test_key":
            return httpx.Response(401, json={"detail": "unauthorized"})

        path = request.url.path
        if request.method == "POST" and path == "/api/v1/run-task":
            payload = json.loads(body.decode("utf-8"))
            assert payload["prompt"] == "extract title"
            assert payload["url"] == "https://example.com"
            return httpx.Response(202, json={"run_id": "run-task-1", "status": "queued"})
        if request.method == "POST" and path == "/api/v1/workflows/wf-1/run":
            return httpx.Response(202, json=_run_out("run-wf-1"))
        if request.method == "GET" and path == "/api/v1/runs/run-1":
            return httpx.Response(200, json=_replay("run-1", "completed"))
        if request.method == "GET" and path == "/api/v1/runs":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "run-1",
                            "workflow_id": "wf-1",
                            "workflow_name": "demo",
                            "workflow_version_id": "wv-1",
                            "version_index": 1,
                            "status": "completed",
                            "queued_at": _utcnow(),
                            "started_at": _utcnow(),
                            "finished_at": _utcnow(),
                            "duration_ms": 100,
                            "error_summary": None,
                            "pending_approval": None,
                            "queue_position": None,
                        }
                    ],
                    "next_cursor": None,
                },
            )
        if request.method == "POST" and path == "/api/v1/runs/run-1/cancel":
            return httpx.Response(200, json=_run_out("run-1", "aborted"))
        if request.method == "GET" and path == "/api/v1/workflows":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "wf-1",
                        "name": "demo",
                        "description": None,
                        "current_version_index": 1,
                        "last_run_status": "completed",
                        "updated_at": _utcnow(),
                    }
                ],
            )
        if request.method == "GET" and path == "/api/v1/credentials":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "cred-1",
                        "name": "token",
                        "type": "generic",
                        "description": None,
                        "field_names": ["token"],
                        "updated_at": _utcnow(),
                        "usage_count": 0,
                    }
                ],
            )
        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    transport._calls = calls  # type: ignore[attr-defined]
    return transport


@pytest.fixture
def client() -> AutoAgent:
    transport = _mock_transport()
    agent = AutoAgent("http://localhost:8000", "sk_test_key", transport=transport)
    agent._test_transport = transport  # type: ignore[attr-defined]
    return agent


def test_run_task_sends_bearer_auth(client: AutoAgent) -> None:
    result = client.run_task("extract title", url="https://example.com")
    assert result.run_id == "run-task-1"
    assert result.status == "queued"
    calls = client._test_transport._calls  # type: ignore[attr-defined]
    assert calls[0][0] == "POST"
    assert calls[0][1].endswith("/api/v1/run-task")


def test_run_workflow(client: AutoAgent) -> None:
    run = client.run_workflow("wf-1", parameters={"x": 1})
    assert run.id == "run-wf-1"
    assert run.status == "queued"


def test_get_run(client: AutoAgent) -> None:
    replay = client.get_run("run-1")
    assert replay.run.status == "completed"
    assert replay.workflow_version.version_index == 1


def test_list_runs(client: AutoAgent) -> None:
    page = client.list_runs(workflow_id="wf-1", limit=10)
    assert len(page.items) == 1
    assert page.items[0].workflow_name == "demo"


def test_cancel_run(client: AutoAgent) -> None:
    run = client.cancel_run("run-1")
    assert run.status == "aborted"


def test_wait_polls_until_terminal(client: AutoAgent, monkeypatch: pytest.MonkeyPatch) -> None:
    statuses = iter(["queued", "running", "completed"])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/runs/run-1":
            status = next(statuses)
            return httpx.Response(200, json=_replay("run-1", status))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    agent = AutoAgent("http://localhost:8000", "sk_test_key", transport=transport)
    sleeps: list[float] = []
    monkeypatch.setattr("auto_agent_sdk.client.time.sleep", lambda s: sleeps.append(s))

    replay = agent.wait("run-1", poll_interval=0.5, max_interval=2.0)
    assert replay.run.status == "completed"
    assert len(sleeps) == 2


def test_workflows_subclient(client: AutoAgent) -> None:
    workflows = client.workflows.list()
    assert workflows[0].name == "demo"


def test_credentials_subclient(client: AutoAgent) -> None:
    creds = client.credentials.list()
    assert creds[0].name == "token"


def test_api_error_on_failure() -> None:
    transport = httpx.MockTransport(
        lambda r: httpx.Response(429, json={"detail": "rate limited"})
    )
    agent = AutoAgent("http://localhost:8000", "sk_test_key", transport=transport)
    with pytest.raises(ApiError) as exc:
        agent.list_runs()
    assert exc.value.status_code == 429


def test_sdk_client_aliases() -> None:
    assert Client is AutoAgent
    assert AsyncClient is AsyncAutoAgent
