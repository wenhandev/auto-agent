"""Desktop sidecar integration tests (API-level, no Playwright)."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.worker.daemon import DaemonState, create_daemon_app
from app.worker import publish_queue as publish_queue_svc


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


@pytest.fixture(autouse=True)
def _clear_publish_queue(tmp_path, monkeypatch):
    queue_file = tmp_path / "publish_queue.json"
    monkeypatch.setattr(publish_queue_svc, "PUBLISH_QUEUE_FILE", queue_file)
    yield


@contextmanager
def daemon_client(state: DaemonState):
    with patch("app.worker.daemon._poll_worker_status", _idle_forever), patch(
        "app.worker.daemon._worker_ws_loop", _idle_forever
    ), patch("app.worker.daemon._run_preflight", return_value=None), patch(
        "app.worker.daemon._flush_publish_queue", new=AsyncMock()
    ), patch("app.worker.daemon._restart_worker_ws", new=AsyncMock()), patch(
        "app.worker.daemon.cred_svc.load_credentials", return_value=FAKE_CREDS
    ):
        app = create_daemon_app(state)
        with TestClient(app) as client:
            yield client


def test_pending_worker_cannot_publish() -> None:
    state = DaemonState(
        approval_status="pending",
        logged_in=True,
        cloud_url="http://127.0.0.1:8001",
        worker_id="wk_test",
    )
    with daemon_client(state) as client, patch(
        "app.worker.daemon.draft_svc.get_draft"
    ) as get_draft:
        get_draft.return_value = {
            "local_id": "draft_1",
            "workflow_id": "wf_1",
            "draft_json": MINIMAL_WORKFLOW,
            "name": "Draft",
        }
        res = client.post("/drafts/draft_1/publish")
    assert res.status_code == 403
    assert "not approved" in res.json()["detail"].lower()


def test_approval_unlocks_publish(monkeypatch) -> None:
    state = DaemonState(
        approval_status="approved",
        logged_in=True,
        cloud_url="http://127.0.0.1:8001",
        worker_id="wk_test",
    )

    def _fake_cloud_post(path: str, body: dict) -> dict:
        assert path.endswith("/versions")
        return {"id": "ver_1", "workflow": body.get("workflow")}

    monkeypatch.setattr("app.worker.daemon.cloud_post", _fake_cloud_post)
    with daemon_client(state) as client, patch(
        "app.worker.daemon.draft_svc.get_draft"
    ) as get_draft, patch("app.worker.daemon.draft_svc.save_draft") as save_draft:
        get_draft.return_value = {
            "local_id": "draft_1",
            "workflow_id": "wf_1",
            "draft_json": MINIMAL_WORKFLOW,
            "name": "Draft",
        }
        res = client.post("/drafts/draft_1/publish")
        assert res.status_code == 200
        assert res.json()["id"] == "ver_1"
        save_draft.assert_called_once()


def test_publish_queues_when_cloud_unreachable(monkeypatch) -> None:
    state = DaemonState(
        approval_status="approved",
        logged_in=True,
        cloud_url="http://127.0.0.1:8001",
        worker_id="wk_test",
    )

    def _raise_connect(*_args, **_kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("app.worker.daemon.cloud_post", _raise_connect)
    with daemon_client(state) as client, patch(
        "app.worker.daemon.draft_svc.get_draft"
    ) as get_draft:
        get_draft.return_value = {
            "local_id": "draft_offline",
            "workflow_id": "wf_1",
            "draft_json": MINIMAL_WORKFLOW,
            "name": "Draft",
        }
        res = client.post("/drafts/draft_offline/publish")
    assert res.status_code == 202
    assert res.json()["status"] == "queued"
    assert publish_queue_svc.is_queued("draft_offline")


def test_publish_queue_flush_after_approval(monkeypatch) -> None:
    publish_queue_svc.enqueue(
        local_id="draft_q",
        workflow_id="wf_1",
        name="Queued draft",
    )

    def _fake_cloud_post(path: str, body: dict) -> dict:
        assert "wf_1" in path
        return {"id": "ver_2", "workflow": body.get("workflow")}

    monkeypatch.setattr("app.worker.daemon.cloud_post", _fake_cloud_post)

    with patch("app.worker.daemon.cred_svc.load_credentials", return_value=FAKE_CREDS), patch(
        "app.worker.daemon.draft_svc.get_draft"
    ) as get_draft, patch("app.worker.daemon.draft_svc.save_draft"):
        get_draft.return_value = {
            "local_id": "draft_q",
            "workflow_id": "wf_1",
            "draft_json": MINIMAL_WORKFLOW,
            "name": "Queued draft",
        }

        from app.worker.daemon import _publish_draft_now

        state = DaemonState(approval_status="approved", logged_in=True)

        def publish_fn(local_id: str) -> dict:
            return _publish_draft_now(state, local_id)

        count = publish_queue_svc.flush_queue(
            publish_fn=publish_fn,
            approval_status="approved",
        )
    assert count == 1
    assert not publish_queue_svc.is_queued("draft_q")
