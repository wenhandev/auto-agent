"""Multi-tenant org isolation and API-key org scoping."""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.auth.api_key import reset_rate_limiter_for_tests
from app.db.models import ApiKey, Organization, Run, User, Workflow, WorkflowVersion
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


def _create_org(session: Session, name: str) -> Organization:
    org = Organization(name=name, created_at=_utcnow())
    session.add(org)
    session.commit()
    session.refresh(org)
    return org


def _api_key_for_org(session: Session, org_id: str, name: str = "test-key") -> tuple[str, dict[str, str]]:
    row, full_key = api_key_svc.create_api_key(session, name=name, org_id=org_id)
    return full_key, {"Authorization": f"Bearer {full_key}"}


def _seed_workflow(session: Session, org_id: str) -> str:
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


def test_bootstrap_creates_default_org_and_admin() -> None:
    with Session(engine) as session:
        org = org_svc.ensure_bootstrap(session)
        assert org.name == org_svc.DEFAULT_ORG_NAME
        admin = session.exec(
            select(User).where(User.email == settings.admin_email)
        ).first()
        assert admin is not None
        assert admin.password_hash


def test_api_key_scoped_to_org(client: TestClient) -> None:
    with Session(engine) as session:
        org_a = _create_org(session, f"org-a-{uuid.uuid4().hex[:6]}")
        org_b = _create_org(session, f"org-b-{uuid.uuid4().hex[:6]}")
        _, headers_a = _api_key_for_org(session, org_a.id)
        _, headers_b = _api_key_for_org(session, org_b.id)
        wf_a = _seed_workflow(session, org_a.id)
        wf_b = _seed_workflow(session, org_b.id)

    listed_a = client.get("/api/v1/workflows", headers=headers_a).json()
    listed_b = client.get("/api/v1/workflows", headers=headers_b).json()
    ids_a = {row["id"] for row in listed_a}
    ids_b = {row["id"] for row in listed_b}
    assert wf_a in ids_a
    assert wf_b not in ids_a
    assert wf_b in ids_b
    assert wf_a not in ids_b


def test_cross_org_workflow_get_returns_404(client: TestClient) -> None:
    with Session(engine) as session:
        org_a = _create_org(session, f"org-a-{uuid.uuid4().hex[:6]}")
        org_b = _create_org(session, f"org-b-{uuid.uuid4().hex[:6]}")
        _, headers_b = _api_key_for_org(session, org_b.id)
        wf_a = _seed_workflow(session, org_a.id)

    resp = client.get(f"/api/v1/workflows/{wf_a}", headers=headers_b)
    assert resp.status_code == 404


def test_cross_org_credential_isolation(client: TestClient) -> None:
    with Session(engine) as session:
        org_a = _create_org(session, f"org-a-{uuid.uuid4().hex[:6]}")
        org_b = _create_org(session, f"org-b-{uuid.uuid4().hex[:6]}")
        _, headers_a = _api_key_for_org(session, org_a.id)
        _, headers_b = _api_key_for_org(session, org_b.id)

    cred_name = f"cred-{uuid.uuid4().hex[:6]}"
    created = client.post(
        "/api/v1/credentials",
        headers=headers_a,
        json={"name": cred_name, "fields": {"token": "secret"}},
    )
    assert created.status_code in (200, 201), created.text
    cred_id = created.json()["id"]

    listed_a = client.get("/api/v1/credentials", headers=headers_a).json()
    assert any(row["id"] == cred_id for row in listed_a)
    assert client.get("/api/v1/credentials", headers=headers_b).json() == []
    assert client.get(f"/api/v1/credentials/{cred_id}", headers=headers_b).status_code == 404


def test_cross_org_run_isolation(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_svc, "_wakeup_dispatcher", lambda: None)
    with Session(engine) as session:
        org_a = _create_org(session, f"org-a-{uuid.uuid4().hex[:6]}")
        org_b = _create_org(session, f"org-b-{uuid.uuid4().hex[:6]}")
        _, headers_b = _api_key_for_org(session, org_b.id)
        wf_a = _seed_workflow(session, org_a.id)
        run = run_svc.enqueue_run(wf_a, session)
        run_id = run.id

    assert client.get(f"/api/v1/runs/{run_id}", headers=headers_b).status_code == 404


def test_internal_routes_use_x_org_id_header(client: TestClient) -> None:
    with Session(engine) as session:
        org_a = _create_org(session, f"org-a-{uuid.uuid4().hex[:6]}")
        org_b = _create_org(session, f"org-b-{uuid.uuid4().hex[:6]}")
        org_a_id = org_a.id
        wf_a = _seed_workflow(session, org_a_id)
        _seed_workflow(session, org_b.id)

    resp = client.get("/api/workflows", headers={"x-org-id": org_a_id})
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert wf_a in ids
    assert len(ids) == 1


def test_rate_limit_per_org(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rate_limit_per_min", 2)
    reset_rate_limiter_for_tests()
    with Session(engine) as session:
        org_a = _create_org(session, f"org-a-{uuid.uuid4().hex[:6]}")
        org_b = _create_org(session, f"org-b-{uuid.uuid4().hex[:6]}")
        _, headers_a = _api_key_for_org(session, org_a.id)
        _, headers_b = _api_key_for_org(session, org_b.id)

    assert client.get("/api/v1/runs", headers=headers_a).status_code == 200
    assert client.get("/api/v1/runs", headers=headers_a).status_code == 200
    assert client.get("/api/v1/runs", headers=headers_a).status_code == 429
    assert client.get("/api/v1/runs", headers=headers_b).status_code == 200


def test_api_keys_list_scoped_to_org(client: TestClient) -> None:
    with Session(engine) as session:
        org_a = _create_org(session, f"org-a-{uuid.uuid4().hex[:6]}")
        org_b = _create_org(session, f"org-b-{uuid.uuid4().hex[:6]}")
        _, headers_a = _api_key_for_org(session, org_a.id, name="key-a")
        _api_key_for_org(session, org_b.id, name="key-b")

    listed = client.get("/api/v1/keys", headers=headers_a).json()
    assert len(listed) == 1
    assert listed[0]["name"] == "key-a"
