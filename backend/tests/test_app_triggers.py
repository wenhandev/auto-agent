from __future__ import annotations

import hashlib
import hmac
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.crypto import encrypt
from app.db.models import Credential, Run, Trigger, Workflow, WorkflowCredential, WorkflowVersion
from app.db.session import engine
from app.integrations import load_integrations
from app.main import app
from app.services import app_subscriptions as app_sub_svc


@pytest.fixture(autouse=True)
def _fresh_registry():
    load_integrations()
    yield


client = TestClient(app)


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


def _setup_app_trigger(*, with_secret: str | None = None) -> tuple[str, str]:
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        cred = f"fixture_key_{uuid.uuid4().hex[:8]}"
        blob = encrypt(json.dumps({"api_key": "secret"}, ensure_ascii=False).encode())
        row = Credential(name=cred, type="fixture_api_key", ciphertext=blob)
        session.add(row)
        session.commit()
        session.refresh(row)
        session.add(WorkflowCredential(workflow_id=wf_id, credential_id=row.id))
        trig = Trigger(
            workflow_id=wf_id,
            type="app",
            schedule_or_path="event_webhook",
            enabled=True,
            app_name="_fixture",
            app_trigger="event_webhook",
            app_credential=cred,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        if with_secret is not None:
            trig.subscription_id = "sub-x"
            trig.subscription_secret_ciphertext = encrypt(with_secret.encode())
        session.add(trig)
        session.commit()
        session.refresh(trig)
        return wf_id, trig.id


def _subscribe_transport() -> httpx.MockTransport:
    return httpx.MockTransport(
        lambda r: httpx.Response(
            200,
            json={"data": {"id": "sub-test-001"}},
            headers={"content-type": "application/json"},
        )
    )


def _sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _reload_trigger(trigger_id: str) -> Trigger:
    with Session(engine) as session:
        row = session.get(Trigger, trigger_id)
        assert row is not None
        session.expunge(row)
        return row


@pytest.mark.asyncio
async def test_subscribe_on_enable():
    wf_id, trig_id = _setup_app_trigger()
    trig = _reload_trigger(trig_id)

    await app_sub_svc.enable_app_trigger(trig, transport=_subscribe_transport())
    with Session(engine) as session:
        row = session.get(Trigger, trig_id)
        assert row is not None
        assert row.subscription_id == "sub-test-001"
        assert row.subscription_secret_ciphertext is not None


@pytest.mark.asyncio
async def test_unsubscribe_on_disable():
    wf_id, trig_id = _setup_app_trigger()
    trig = _reload_trigger(trig_id)
    await app_sub_svc.enable_app_trigger(trig, transport=_subscribe_transport())
    trig = _reload_trigger(trig_id)

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={"data": {"ok": True}})

    await app_sub_svc.disable_app_trigger(trig, transport=httpx.MockTransport(handler))
    assert any("hooks" in u for u in calls)
    with Session(engine) as session:
        row = session.get(Trigger, trig_id)
        assert row is not None
        assert row.subscription_id is None


def test_challenge_echo():
    wf_id, trig_id = _setup_app_trigger(with_secret="secret-abc")

    resp = client.post(
        f"/api/triggers/app/{trig_id}",
        json={"challenge": "abc123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "challenge"
    assert data["challenge"] == "abc123"
    with Session(engine) as session:
        assert len(session.exec(select(Run).where(Run.workflow_id == wf_id)).all()) == 0


def test_valid_signature_enqueues_run():
    secret = "whsec-test"
    wf_id, trig_id = _setup_app_trigger(with_secret=secret)

    payload = {
        "event_id": "evt-1",
        "event": {"id": "m1", "text": "hello"},
    }
    raw = json.dumps(payload).encode()
    resp = client.post(
        f"/api/triggers/app/{trig_id}",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Fixture-Signature": _sign(raw, secret),
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    with Session(engine) as session:
        runs = session.exec(select(Run).where(Run.workflow_id == wf_id)).all()
        assert len(runs) == 1
        ctx = json.loads(runs[0].trigger_context_json or "{}")
        assert ctx["context"]["text"] == "hello"


def test_invalid_signature_rejected():
    wf_id, trig_id = _setup_app_trigger(with_secret="secret-abc")

    payload = {"event_id": "evt-2", "event": {"id": "m2"}}
    raw = json.dumps(payload).encode()
    resp = client.post(
        f"/api/triggers/app/{trig_id}",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Fixture-Signature": "sha256=deadbeef",
        },
    )
    assert resp.status_code == 401


def test_provider_retry_deduped():
    secret = "whsec-dedup"
    wf_id, trig_id = _setup_app_trigger(with_secret=secret)

    payload = {"event_id": "evt-dup", "event": {"id": "m3", "text": "once"}}
    raw = json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Fixture-Signature": _sign(raw, secret),
    }
    r1 = client.post(f"/api/triggers/app/{trig_id}", content=raw, headers=headers)
    r2 = client.post(f"/api/triggers/app/{trig_id}", content=raw, headers=headers)
    assert r1.json()["status"] == "queued"
    assert r2.json()["status"] == "duplicate"
    with Session(engine) as session:
        runs = session.exec(select(Run).where(Run.workflow_id == wf_id)).all()
        assert len(runs) == 1


def test_create_app_trigger_via_api(monkeypatch):
    async def fake_enable(trig, **kwargs):
        app_sub_svc.persist_subscription(trig.id, "sub-api", "sec-api")

    monkeypatch.setattr(app_sub_svc, "enable_app_trigger", fake_enable)

    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        cred = f"fixture_key_{uuid.uuid4().hex[:8]}"
        blob = encrypt(json.dumps({"api_key": "secret"}, ensure_ascii=False).encode())
        row = Credential(name=cred, type="fixture_api_key", ciphertext=blob)
        session.add(row)
        session.commit()
        session.refresh(row)
        session.add(WorkflowCredential(workflow_id=wf_id, credential_id=row.id))
        session.commit()

    resp = client.post(
        f"/api/workflows/{wf_id}/triggers",
        json={
            "type": "app",
            "enabled": True,
            "app_name": "_fixture",
            "app_trigger": "event_webhook",
            "app_credential": cred,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["subscription_status"] == "active"
    assert data["subscription_id"] == "sub-api"
