from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.crypto import encrypt
from app.db.models import ApiKey, Trigger, WebhookDelivery, WebhookSubscription, Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.main import app
from app.sdk.webhook_verify import verify_webhook
from app.services import webhooks as webhook_svc
from app.services.webhook_signing import DELIVERY_ID_HEADER, SIGNATURE_HEADER, sign_body


@pytest.fixture(autouse=True)
def _fresh_db():
    init_db()
    with Session(engine) as session:
        for row in session.exec(select(ApiKey)).all():
            session.delete(row)
        for row in session.exec(select(WebhookDelivery)).all():
            session.delete(row)
        for row in session.exec(select(WebhookSubscription)).all():
            session.delete(row)
        session.commit()
    yield


client = TestClient(app)


def _auth_headers() -> dict[str, str]:
    resp = client.post("/api/v1/keys", json={"name": "webhook-tests"})
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['key']}"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _seed_workflow(session: Session) -> str:
    wf = Workflow(name=f"wf-{uuid.uuid4().hex[:6]}", created_at=_utcnow(), updated_at=_utcnow())
    session.add(wf)
    session.commit()
    session.refresh(wf)
    ver = WorkflowVersion(
        workflow_id=wf.id,
        version_index=1,
        nodes_json="[]",
        edges_json="[]",
        start_id="n1",
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


def _public_url() -> str:
    return "https://example.com/hook"


def test_sign_body_format():
    body = b'{"event":"run_completed"}'
    secret = "test-secret"
    sig = sign_body(body, secret)
    assert sig.startswith("sha256=")
    assert verify_webhook(body, secret, sig)


def test_ssrf_rejects_loopback_on_create():
    resp = client.post(
        "/api/v1/webhooks",
        headers=_auth_headers(),
        json={"url": "http://localhost/hook", "events": ["run_completed"]},
    )
    assert resp.status_code == 422
    assert "blocked" in resp.json()["detail"].lower()


def test_subscription_crud():
    headers = _auth_headers()
    resp = client.post(
        "/api/v1/webhooks",
        headers=headers,
        json={"url": _public_url(), "events": ["run_completed", "run_failed"], "secret": "s3cret"},
    )
    assert resp.status_code == 201
    sub = resp.json()
    assert sub["url"] == _public_url()
    assert sub["secret_masked"].startswith("***") or "***" in sub["secret_masked"]

    sub_id = sub["id"]
    resp = client.get(f"/api/v1/webhooks/{sub_id}", headers=headers)
    assert resp.status_code == 200

    resp = client.patch(
        f"/api/v1/webhooks/{sub_id}",
        headers=headers,
        json={"enabled": False},
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    resp = client.delete(f"/api/v1/webhooks/{sub_id}", headers=headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delivery_signs_and_posts():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        captured["signature"] = request.headers.get(SIGNATURE_HEADER)
        captured["delivery_id"] = request.headers.get(DELIVERY_ID_HEADER)
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    secret = "signing-key"
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        sub = WebhookSubscription(
            url=_public_url(),
            events=["run_completed"],
            secret_ciphertext=encrypt(secret.encode()),
            enabled=True,
            workflow_id=wf_id,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(sub)
        session.commit()
        session.refresh(sub)
        sub_id = sub.id

    delivery_ids = webhook_svc.enqueue_event(
        "run_completed",
        run_id="run-1",
        workflow_id=wf_id,
        status="completed",
        extra={"output": "ok"},
    )
    assert len(delivery_ids) == 1
    delivery_id = delivery_ids[0]

    result = await webhook_svc.execute_delivery(delivery_id, transport=transport)
    assert result.status == "delivered"
    assert result.attempt == 1
    assert captured["signature"] == sign_body(captured["body"], secret)
    assert captured["delivery_id"] == delivery_id
    payload = json.loads(captured["body"])
    assert payload["delivery_id"] == delivery_id
    assert verify_webhook(captured["body"], secret, captured["signature"])


@pytest.mark.asyncio
async def test_backoff_on_failure():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    with Session(engine) as session:
        sub = WebhookSubscription(
            url=_public_url(),
            events=["run_failed"],
            secret_ciphertext=encrypt(b"key"),
            enabled=True,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(sub)
        session.commit()
        session.refresh(sub)

    delivery_ids = webhook_svc.enqueue_event(
        "run_failed", run_id="r1", workflow_id=None, status="failed"
    )
    delivery_id = delivery_ids[0]

    with patch.object(webhook_svc.settings, "webhook_max_attempts", 3):
        result = await webhook_svc.execute_delivery(delivery_id, transport=transport)
    assert result.status == "failed"
    assert result.attempt == 1
    assert result.response_code == 500
    assert result.next_attempt_at is not None
    next_at = result.next_attempt_at
    if next_at.tzinfo is None:
        next_at = next_at.replace(tzinfo=timezone.utc)
    assert next_at > _utcnow()

    with patch.object(webhook_svc.settings, "webhook_max_attempts", 3):
        result = await webhook_svc.execute_delivery(delivery_id, transport=transport)
        result = await webhook_svc.execute_delivery(delivery_id, transport=transport)
    assert result.status == "exhausted"
    assert result.attempt == 3


@pytest.mark.asyncio
async def test_replay_resets_and_redelivers():
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    with Session(engine) as session:
        sub = WebhookSubscription(
            url=_public_url(),
            events=["run_aborted"],
            secret_ciphertext=encrypt(b"key"),
            enabled=True,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(sub)
        session.commit()
        delivery_ids = webhook_svc.enqueue_event(
            "run_aborted", run_id="r1", workflow_id=None, status="aborted"
        )
        delivery_id = delivery_ids[0]
        row = session.get(WebhookDelivery, delivery_id)
        assert row is not None
        row.status = "exhausted"
        row.attempt = 3
        session.add(row)
        session.commit()

    webhook_svc.replay_delivery(delivery_id)
    with Session(engine) as session:
        row = session.get(WebhookDelivery, delivery_id)
        assert row is not None
        assert row.status == "pending"

    await webhook_svc.execute_delivery(delivery_id, transport=transport)
    assert calls["n"] == 1
    with Session(engine) as session:
        row = session.get(WebhookDelivery, delivery_id)
        assert row is not None
        assert row.status == "delivered"


def test_reload_pending_deliveries_schedules_rows():
    with Session(engine) as session:
        sub = WebhookSubscription(
            url=_public_url(),
            events=["run_completed"],
            secret_ciphertext=encrypt(b"key"),
            enabled=True,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(sub)
        session.commit()
        session.refresh(sub)
        delivery = WebhookDelivery(
            subscription_id=sub.id,
            event="run_completed",
            payload_json='{"event":"run_completed","delivery_id":"x"}',
            attempt=1,
            status="failed",
            next_attempt_at=_utcnow() + timedelta(minutes=5),
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(delivery)
        session.commit()
        delivery_id = delivery.id

    scheduled: list[str] = []

    class _FakeScheduler:
        def add_job(self, *_args, **kwargs):
            scheduled.append(kwargs.get("id") or kwargs.get("args", [None])[0])

    with patch(
        "app.services.scheduler.get_scheduler",
        return_value=_FakeScheduler(),
    ):
        count = webhook_svc.reload_pending_deliveries()

    assert count >= 1
    assert f"webhook:{delivery_id}" in scheduled


def test_scoped_subscription_filters_by_workflow():
    with Session(engine) as session:
        wf_a = _seed_workflow(session)
        wf_b = _seed_workflow(session)
        sub = WebhookSubscription(
            url=_public_url(),
            events=["run_completed"],
            secret_ciphertext=encrypt(b"key"),
            enabled=True,
            workflow_id=wf_a,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(sub)
        session.commit()

    ids_a = webhook_svc.enqueue_event(
        "run_completed", run_id="r1", workflow_id=wf_a, status="completed"
    )
    ids_b = webhook_svc.enqueue_event(
        "run_completed", run_id="r2", workflow_id=wf_b, status="completed"
    )
    assert len(ids_a) == 1
    assert len(ids_b) == 0


def test_inbound_hmac_trigger():
    secret = "inbound-hmac-secret"
    body = b'{"hello":"world"}'
    signature = sign_body(body, secret)

    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        trig = Trigger(
            workflow_id=wf_id,
            type="webhook",
            schedule_or_path=f"path-{uuid.uuid4().hex[:8]}",
            enabled=True,
            secret_ciphertext=encrypt(secret.encode()),
            auth_mode="hmac",
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(trig)
        session.commit()
        path = trig.schedule_or_path

    resp = client.post(
        f"/api/triggers/webhook/{path}",
        content=body,
        headers={SIGNATURE_HEADER: signature, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"

    resp = client.post(
        f"/api/triggers/webhook/{path}",
        content=body,
        headers={SIGNATURE_HEADER: "sha256=deadbeef", "Content-Type": "application/json"},
    )
    assert resp.status_code == 401


def test_test_event_endpoint():
    with Session(engine) as session:
        sub = WebhookSubscription(
            url=_public_url(),
            events=["approval_requested"],
            secret_ciphertext=encrypt(b"key"),
            enabled=True,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(sub)
        session.commit()
        session.refresh(sub)
        sub_id = sub.id

    resp = client.post(f"/api/v1/webhooks/{sub_id}/test", headers=_auth_headers())
    assert resp.status_code == 200
    delivery_id = resp.json()["delivery_id"]
    with Session(engine) as session:
        row = session.get(WebhookDelivery, delivery_id)
        assert row is not None
        assert row.status == "pending"
