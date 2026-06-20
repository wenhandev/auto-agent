"""Tests for API key auth and the /api/v1 public surface."""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.auth.api_key import reset_rate_limiter_for_tests
from app.db.models import ApiKey, Organization, Run, Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.main import app
from app.services import api_keys as api_key_svc
from app.services import orgs as org_svc
from app.services import runs as run_svc
from app.settings import settings


@pytest.fixture(autouse=True)
def _fresh_api_keys():
    init_db()
    reset_rate_limiter_for_tests()
    with Session(engine) as session:
        for row in session.exec(select(ApiKey)).all():
            session.delete(row)
        session.commit()
    yield
    reset_rate_limiter_for_tests()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def bootstrap_api_key(client: TestClient, name: str = "test-key") -> tuple[str, dict[str, str]]:
    resp = client.post("/api/v1/keys", json={"name": name})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    full_key = body["key"]
    assert full_key.startswith("sk_")
    headers = {"Authorization": f"Bearer {full_key}"}
    return full_key, headers


def _seed_workflow(session: Session) -> str:
    org_id = org_svc.get_default_org_id(session)
    wf = Workflow(
        name=f"wf-{uuid.uuid4().hex[:6]}",
        org_id=org_id,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    session.add(wf)
    session.commit()
    session.refresh(wf)
    ver = WorkflowVersion(
        workflow_id=wf.id,
        version_index=1,
        nodes_json='[{"id":"start","type":"start","label":"S","params":{}}]',
        edges_json="[]",
        start_id="start",
        authored_by="test",
        created_at=_utcnow(),
    )
    session.add(ver)
    session.commit()
    session.refresh(ver)
    wf.current_version_id = ver.id
    session.add(wf)
    session.commit()
    return wf.id


def test_bootstrap_first_key_without_auth(client: TestClient) -> None:
    resp = client.post("/api/v1/keys", json={"name": "bootstrap"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["key"].startswith("sk_")
    assert "key" not in client.get("/api/v1/keys", headers={"Authorization": f"Bearer {body['key']}"}).json()[0]


def test_reveal_once_and_list_prefix_only(client: TestClient) -> None:
    full_key, headers = bootstrap_api_key(client)
    resp = client.get("/api/v1/keys", headers=headers)
    assert resp.status_code == 200
    row = resp.json()[0]
    assert row["prefix"].endswith("…")
    assert full_key not in str(row)
    assert "key" not in row


def test_revoke_key(client: TestClient) -> None:
    full_key, headers = bootstrap_api_key(client)
    listed = client.get("/api/v1/keys", headers=headers).json()
    key_id = listed[0]["id"]
    resp = client.delete(f"/api/v1/keys/{key_id}", headers=headers)
    assert resp.status_code == 204
    resp = client.get("/api/v1/runs", headers=headers)
    assert resp.status_code == 401


def test_missing_key_returns_401(client: TestClient) -> None:
    bootstrap_api_key(client)
    resp = client.get("/api/v1/runs")
    assert resp.status_code == 401


def test_invalid_key_returns_401(client: TestClient) -> None:
    bootstrap_api_key(client)
    resp = client.get("/api/v1/runs", headers={"Authorization": "Bearer sk_invalid"})
    assert resp.status_code == 401


def test_x_api_key_header(client: TestClient) -> None:
    full_key, _ = bootstrap_api_key(client)
    resp = client.get("/api/v1/runs", headers={"x-api-key": full_key})
    assert resp.status_code == 200


def test_revoked_key_not_accepted_and_last_used_untouched(client: TestClient) -> None:
    full_key, headers = bootstrap_api_key(client)
    client.get("/api/v1/runs", headers=headers)
    with Session(engine) as session:
        row = session.exec(select(ApiKey)).first()
        assert row is not None
        last_used = row.last_used_at
        api_key_svc.revoke_api_key(session, row.id)
    resp = client.get("/api/v1/runs", headers=headers)
    assert resp.status_code == 401
    with Session(engine) as session:
        row = session.get(ApiKey, row.id)  # type: ignore[arg-type]
        assert row is not None
        assert row.last_used_at == last_used


def test_valid_key_updates_last_used(client: TestClient) -> None:
    full_key, headers = bootstrap_api_key(client)
    with Session(engine) as session:
        row = session.exec(select(ApiKey)).first()
        assert row is not None
        assert row.last_used_at is None
    resp = client.get("/api/v1/runs", headers=headers)
    assert resp.status_code == 200
    with Session(engine) as session:
        row = session.exec(select(ApiKey)).first()
        assert row is not None
        assert row.last_used_at is not None


def test_internal_routes_exempt(client: TestClient) -> None:
    bootstrap_api_key(client)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    resp = client.get("/api/runs")
    assert resp.status_code == 200


def test_run_task_creates_run(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _, headers = bootstrap_api_key(client)
    monkeypatch.setattr(run_svc, "_wakeup_dispatcher", lambda: None)

    resp = client.post(
        "/api/v1/run-task",
        headers=headers,
        json={"prompt": "find the title", "url": "https://example.com"},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    run_id = body["run_id"]

    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.source == "api"
        ctx = __import__("json").loads(run.trigger_context_json or "{}")
        assert ctx["kind"] == "api"
        assert "api_key_id" in ctx


def test_workflow_run_sets_trigger_context(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _, headers = bootstrap_api_key(client)
    monkeypatch.setattr(run_svc, "_wakeup_dispatcher", lambda: None)
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        key_id = session.exec(select(ApiKey)).first().id  # type: ignore[union-attr]

    resp = client.post(f"/api/v1/workflows/{wf_id}/run", headers=headers, json={})
    assert resp.status_code == 202, resp.text
    run_id = resp.json()["id"]
    with Session(engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        ctx = __import__("json").loads(run.trigger_context_json or "{}")
        assert ctx == {"kind": "api", "api_key_id": key_id}


def test_cancel_run(client: TestClient) -> None:
    _, headers = bootstrap_api_key(client)
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        run = run_svc.enqueue_run(wf_id, session)
        run_id = run.id
    run_svc.remove_from_queue_for_tests(run_id)

    resp = client.post(f"/api/v1/runs/{run_id}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "aborted"


def test_runs_pagination(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _, headers = bootstrap_api_key(client)
    monkeypatch.setattr(run_svc, "_wakeup_dispatcher", lambda: None)
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        for _ in range(3):
            run_svc.enqueue_run(wf_id, session)

    resp = client.get("/api/v1/runs?limit=2", headers=headers)
    assert resp.status_code == 200
    page = resp.json()
    assert len(page["items"]) == 2
    assert page["next_cursor"]

    resp2 = client.get(f"/api/v1/runs?limit=2&cursor={page['next_cursor']}", headers=headers)
    assert resp2.status_code == 200
    assert len(resp2.json()["items"]) >= 1


def test_rate_limit_returns_429(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _, headers = bootstrap_api_key(client)
    monkeypatch.setattr(settings, "rate_limit_per_min", 2)
    reset_rate_limiter_for_tests()

    assert client.get("/api/v1/runs", headers=headers).status_code == 200
    assert client.get("/api/v1/runs", headers=headers).status_code == 200
    resp = client.get("/api/v1/runs", headers=headers)
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_openapi_lists_v1_with_security(client: TestClient) -> None:
    bootstrap_api_key(client)
    schema = client.get("/openapi.json").json()
    assert "/api/v1/run-task" in schema["paths"]
    assert "/api/v1/keys" in schema["paths"]
    assert "BearerAuth" in schema["components"]["securitySchemes"]
    run_task_post = schema["paths"]["/api/v1/run-task"]["post"]
    assert "security" in run_task_post


def test_credentials_masked(client: TestClient) -> None:
    _, headers = bootstrap_api_key(client)
    resp = client.post(
        "/api/v1/credentials",
        headers=headers,
        json={"name": f"cred-{uuid.uuid4().hex[:6]}", "fields": {"token": "super-secret-value"}},
    )
    assert resp.status_code == 200 or resp.status_code == 201
    body = resp.json()
    masked = body["fields"][0]["masked_value"]
    assert "super-secret-value" not in masked
