"""Tests for the desktop runtime sidecar HTTP API."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.worker.daemon import DaemonState, create_daemon_app
from app.worker.local_runs import LocalRunManager


async def _idle_forever(_state: DaemonState | None = None) -> None:
    await asyncio.Event().wait()


FAKE_CREDS = {
    "cloud_url": "http://127.0.0.1:8001",
    "worker_session_token": "wk_sess_test",
    "web_session_token": "web_sess_test",
    "worker_id": "wk_test",
    "org_id": "org_test",
}

MINIMAL_WORKFLOW = {
    "nodes": [{"id": "start", "type": "start", "label": "Start", "params": {}}],
    "edges": [],
    "start_id": "start",
}


@pytest.fixture
def daemon_client() -> TestClient:
    state = DaemonState(
        approval_status="approved",
        logged_in=True,
        cloud_url="http://127.0.0.1:8001",
        worker_id="wk_test",
        environment={"environment_status": "ready", "checks": []},
    )
    with patch("app.worker.daemon._poll_worker_status", _idle_forever), patch(
        "app.worker.daemon._worker_ws_loop", _idle_forever
    ), patch("app.worker.daemon._run_preflight", return_value=None), patch(
        "app.worker.daemon._restart_worker_ws", new=AsyncMock()
    ), patch("app.worker.daemon._flush_publish_queue", new=AsyncMock()), patch(
        "app.worker.daemon.cred_svc.load_credentials", return_value=FAKE_CREDS
    ):
        app = create_daemon_app(state)
        with TestClient(app) as client:
            yield client


def test_daemon_health(daemon_client: TestClient) -> None:
    res = daemon_client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_daemon_ready(daemon_client: TestClient) -> None:
    with patch("app.worker.daemon.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.get.return_value.status_code = 200
        res = daemon_client.get("/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["sidecar"] is True
    assert data["cloud"] is True
    assert data["status"] == "ok"


def test_daemon_status(daemon_client: TestClient) -> None:
    res = daemon_client.get("/status")
    assert res.status_code == 200
    data = res.json()
    assert data["approval_status"] == "approved"
    assert data["logged_in"] is True
    assert data["preflight"]["environment_status"] == "ready"


def test_daemon_runs_blocked_when_pending() -> None:
    state = DaemonState(
        approval_status="pending",
        logged_in=True,
        cloud_url="http://127.0.0.1:8001",
        worker_id="wk_test",
    )
    with patch("app.worker.daemon._poll_worker_status", _idle_forever), patch(
        "app.worker.daemon._worker_ws_loop", _idle_forever
    ), patch("app.worker.daemon._run_preflight", return_value=None), patch(
        "app.worker.daemon._restart_worker_ws", new=AsyncMock()
    ), patch("app.worker.daemon._flush_publish_queue", new=AsyncMock()), patch(
        "app.worker.daemon.cred_svc.load_credentials", return_value=FAKE_CREDS
    ):
        app = create_daemon_app(state)
        with TestClient(app) as client:
            res = client.post("/runs", json={"workflow": MINIMAL_WORKFLOW})
    assert res.status_code == 403
    assert "not approved" in res.json()["detail"].lower()


def test_daemon_start_run_when_approved() -> None:
    async def _fake_start_run(self, **kwargs):  # type: ignore[no-untyped-def]
        return {
            "id": "local_test123",
            "workflow_id": kwargs.get("workflow_id"),
            "status": "running",
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": None,
        }

    state = DaemonState(
        approval_status="approved",
        logged_in=True,
        cloud_url="http://127.0.0.1:8001",
        worker_id="wk_test",
    )
    with patch("app.worker.daemon._poll_worker_status", _idle_forever), patch(
        "app.worker.daemon._worker_ws_loop", _idle_forever
    ), patch("app.worker.daemon._run_preflight", return_value=None), patch(
        "app.worker.daemon._restart_worker_ws", new=AsyncMock()
    ), patch("app.worker.daemon._flush_publish_queue", new=AsyncMock()), patch(
        "app.worker.daemon.cred_svc.load_credentials", return_value=FAKE_CREDS), patch.object(
        LocalRunManager, "start_run", _fake_start_run
    ), patch("app.worker.local_runs.require_configured"):
        app = create_daemon_app(state)
        with TestClient(app) as client:
            res = client.post("/runs", json={"workflow": MINIMAL_WORKFLOW})
    assert res.status_code == 201
    assert res.json()["id"] == "local_test123"


def test_daemon_abort_run() -> None:
    state = DaemonState(
        approval_status="approved",
        logged_in=True,
        cloud_url="http://127.0.0.1:8001",
        worker_id="wk_test",
    )
    state.runs._active["local_abort1"] = asyncio.Event()
    with patch("app.worker.daemon._poll_worker_status", _idle_forever), patch(
        "app.worker.daemon._worker_ws_loop", _idle_forever
    ), patch("app.worker.daemon._run_preflight", return_value=None), patch(
        "app.worker.daemon._restart_worker_ws", new=AsyncMock()
    ), patch("app.worker.daemon._flush_publish_queue", new=AsyncMock()), patch(
        "app.worker.daemon.cred_svc.load_credentials", return_value=FAKE_CREDS):
        app = create_daemon_app(state)
        with TestClient(app) as client:
            state.runs.get_run = lambda _rid: {  # type: ignore[method-assign]
                "id": "local_abort1",
                "status": "running",
            }
            res = client.post("/runs/local_abort1/abort")
    assert res.status_code == 200
    assert res.json()["status"] == "abort_requested"
    assert state.runs._active["local_abort1"].is_set()


def test_daemon_runs_requires_llm_config(daemon_client: TestClient) -> None:
    with patch(
        "app.worker.local_runs.require_configured",
        side_effect=RuntimeError("Local LLM is not configured"),
    ):
        res = daemon_client.post("/runs", json={"workflow": MINIMAL_WORKFLOW})
    assert res.status_code == 400
    assert "LLM" in res.json()["detail"]


def test_daemon_llm_settings_encrypted_roundtrip(
    daemon_client: TestClient, tmp_path, monkeypatch
) -> None:
    from app.worker import local_llm as llm_svc

    config_file = tmp_path / "llm.json"
    key_file = tmp_path / ".key"
    monkeypatch.setattr(llm_svc, "LLM_CONFIG_FILE", config_file)
    monkeypatch.setattr(llm_svc, "LLM_KEY_FILE", key_file)
    monkeypatch.setattr(llm_svc, "_fernet", None)

    payload = {
        "llm_provider": "openai",
        "openai_api_key": "sk-test-secret",
        "openai_model": "gpt-4o",
    }
    res = daemon_client.put("/settings/llm", json=payload)
    assert res.status_code == 200
    assert res.json()["openai_api_key"].startswith("***")

    raw = config_file.read_text(encoding="utf-8")
    assert raw.startswith("gAAAA")
    assert "sk-test-secret" not in raw

    loaded = llm_svc.load_config()
    assert loaded["openai_api_key"] == "sk-test-secret"


def test_daemon_publish_blocked_when_pending() -> None:
    state = DaemonState(
        approval_status="pending",
        logged_in=True,
        cloud_url="http://127.0.0.1:8001",
        worker_id="wk_test",
    )
    with patch("app.worker.daemon._poll_worker_status", _idle_forever), patch(
        "app.worker.daemon._worker_ws_loop", _idle_forever
    ), patch("app.worker.daemon._run_preflight", return_value=None), patch(
        "app.worker.daemon._restart_worker_ws", new=AsyncMock()
    ), patch("app.worker.daemon._flush_publish_queue", new=AsyncMock()), patch(
        "app.worker.daemon.cred_svc.load_credentials", return_value=FAKE_CREDS
    ), patch("app.worker.daemon.draft_svc.get_draft") as get_draft:
        get_draft.return_value = {
            "local_id": "draft_1",
            "workflow_id": "wf_1",
            "draft_json": MINIMAL_WORKFLOW,
        }
        app = create_daemon_app(state)
        with TestClient(app) as client:
            res = client.post("/drafts/draft_1/publish")
    assert res.status_code == 403


def test_daemon_publish_queues_offline(monkeypatch, tmp_path) -> None:
    from app.worker import publish_queue as publish_queue_svc

    queue_file = tmp_path / "publish_queue.json"
    monkeypatch.setattr(publish_queue_svc, "PUBLISH_QUEUE_FILE", queue_file)

    state = DaemonState(
        approval_status="approved",
        logged_in=True,
        cloud_url="http://127.0.0.1:8001",
        worker_id="wk_test",
    )

    def _offline(*_args, **_kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("app.worker.daemon.cloud_post", _offline)
    with patch("app.worker.daemon._poll_worker_status", _idle_forever), patch(
        "app.worker.daemon._worker_ws_loop", _idle_forever
    ), patch("app.worker.daemon._run_preflight", return_value=None), patch(
        "app.worker.daemon._restart_worker_ws", new=AsyncMock()
    ), patch("app.worker.daemon._flush_publish_queue", new=AsyncMock()), patch(
        "app.worker.daemon.cred_svc.load_credentials", return_value=FAKE_CREDS
    ), patch("app.worker.daemon.draft_svc.get_draft") as get_draft:
        get_draft.return_value = {
            "local_id": "draft_off",
            "workflow_id": "wf_1",
            "draft_json": MINIMAL_WORKFLOW,
        }
        app = create_daemon_app(state)
        with TestClient(app) as client:
            res = client.post("/drafts/draft_off/publish")
    assert res.status_code == 202
    assert publish_queue_svc.is_queued("draft_off")
    publish_queue_svc.dequeue("draft_off")
