"""Worker registration, login, and dispatch tests."""

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
from app.auth.session import reset_login_rate_limiter_for_tests
from app.db.models import ApiKey, Organization, OrgMembership, Run, User, Worker
from app.db.session import engine, init_db
from app.db.migrations import ensure_run_worker_columns, ensure_worker_tables, ensure_desktop_client_columns
from app.main import app
from app.services import orgs as org_svc
from app.services import runs as run_svc
from app.services import worker_hub
from app.services import worker_sessions as worker_session_svc


@pytest.fixture(autouse=True)
def _fresh_state():
    init_db()
    ensure_worker_tables()
    ensure_desktop_client_columns()
    ensure_run_worker_columns()
    reset_rate_limiter_for_tests()
    reset_login_rate_limiter_for_tests()
    run_svc.reset_dispatcher_for_tests()
    worker_hub.reset_for_tests()
    with Session(engine) as session:
        for row in session.exec(select(ApiKey)).all():
            session.delete(row)
        session.commit()
    yield
    run_svc.reset_dispatcher_for_tests()
    worker_hub.reset_for_tests()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _bootstrap_user(
    session: Session,
    email: str,
    password: str,
    *,
    role: str = "admin",
) -> tuple[User, Organization]:
    org = org_svc.ensure_bootstrap(session)
    user = User(
        email=email,
        password_hash=org_svc.hash_password(password),
        name="test",
        created_at=_utcnow(),
    )
    session.add(user)
    session.flush()
    session.add(
        OrgMembership(
            user_id=user.id,
            org_id=org.id,
            role=role,
            created_at=_utcnow(),
        )
    )
    session.commit()
    session.refresh(user)
    return user, org


def _set_org_policy(session: Session, org_id: str, policy: str) -> None:
    org = session.get(Organization, org_id)
    assert org is not None
    org.desktop_client_policy = policy
    session.add(org)
    session.commit()


def _worker_login(
    client: TestClient,
    *,
    email: str,
    password: str,
    machine_id: str,
) -> dict:
    res = client.post(
        "/api/v1/workers/login",
        json={
            "email": email,
            "password": password,
            "machine_id": machine_id,
            "hostname": "test-host",
            "environment": {"environment_status": "ready", "checks": []},
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


def _web_login(client: TestClient, email: str, password: str) -> str:
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["token"]


def test_worker_login_and_list(client: TestClient) -> None:
    email = f"worker-{uuid.uuid4().hex[:8]}@example.com"
    password = "secret-pass"
    with Session(engine) as session:
        _bootstrap_user(session, email, password)

    machine_id = f"machine-{uuid.uuid4().hex}"
    res = client.post(
        "/api/v1/workers/login",
        json={
            "email": email,
            "password": password,
            "machine_id": machine_id,
            "hostname": "test-host",
            "environment": {"environment_status": "ready", "checks": []},
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["worker_session_token"].startswith("wk_sess_")
    assert data["worker_id"]

    with Session(engine) as session:
        worker = session.get(Worker, data["worker_id"])
        assert worker is not None
        assert worker.machine_id == machine_id
        looked_up = worker_session_svc.lookup_worker_by_token(
            session,
            data["worker_session_token"],
        )
        assert looked_up is not None


def test_list_queued_worker_run_ids(client: TestClient) -> None:
    from app.db.models import Workflow, WorkflowVersion
    from app.schemas import Edge, Node, Workflow as WorkflowSchema

    wf_schema = WorkflowSchema(
        nodes=[
            Node(id="start", type="start", label="start"),
            Node(id="end", type="end", label="end"),
        ],
        edges=[Edge(id="e1", source="start", target="end")],
        start_id="start",
    )
    with Session(engine) as session:
        org = org_svc.ensure_bootstrap(session)
        wf = Workflow(name="wf-worker", org_id=org.id)
        session.add(wf)
        session.flush()
        ver = WorkflowVersion(
            workflow_id=wf.id,
            version_index=1,
            nodes_json="[]",
            edges_json="[]",
            start_id="start",
            authored_by="test",
        )
        ver.nodes_json = __import__("json").dumps(wf_schema.model_dump()["nodes"])
        ver.edges_json = __import__("json").dumps(wf_schema.model_dump()["edges"])
        session.add(ver)
        session.flush()
        wf.current_version_id = ver.id
        session.add(wf)
        session.commit()
        run = run_svc.enqueue_run(
            wf.id,
            session,
            execution_mode="worker",
            worker_pool="default",
        )
        run_id = run.id

    queued = run_svc.list_queued_worker_run_ids()
    assert run_id in queued


def test_ingest_worker_event_updates_run(client: TestClient) -> None:
    from app.db.models import Workflow, WorkflowVersion

    with Session(engine) as session:
        org = org_svc.ensure_bootstrap(session)
        wf = Workflow(name="wf-events", org_id=org.id)
        session.add(wf)
        session.flush()
        ver = WorkflowVersion(
            workflow_id=wf.id,
            version_index=1,
            nodes_json="[]",
            edges_json="[]",
            start_id="start",
            authored_by="test",
        )
        session.add(ver)
        session.flush()
        wf.current_version_id = ver.id
        session.add(wf)
        run = Run(
            workflow_id=wf.id,
            workflow_version_id=ver.id,
            org_id=org.id,
            status="running",
            execution_mode="worker",
        )
        session.add(run)
        session.commit()
        run_id = run.id

    import asyncio

    asyncio.run(
        run_svc.ingest_worker_event(
            run_id,
            0,
            {"event": "run_completed", "node_id": None, "ts": _utcnow().isoformat()},
        )
    )
    with Session(engine) as session:
        row = session.get(Run, run_id)
        assert row is not None
        assert row.status == "completed"


def test_ingest_worker_event_rejects_stale_seq() -> None:
    import asyncio

    run_id = f"run-stale-{uuid.uuid4().hex[:8]}"
    asyncio.run(
        run_svc.ingest_worker_event(
            run_id,
            5,
            {"event": "node_started", "node_id": "n1", "ts": _utcnow().isoformat()},
        )
    )
    asyncio.run(
        run_svc.ingest_worker_event(
            run_id,
            3,
            {"event": "node_started", "node_id": "n1", "ts": _utcnow().isoformat()},
        )
    )


def test_env_aware_assignment_not_ready_skipped() -> None:
    from app.services.worker_hub import WorkerConnection, is_worker_assignable

    conn = WorkerConnection(
        worker_id="w1",
        org_id="org",
        websocket=object(),  # type: ignore[arg-type]
        environment_status="not_ready",
    )
    assert is_worker_assignable(conn, worker_pool="default") is False


def test_env_aware_assignment_degraded_without_chromium() -> None:
    from app.services.worker_hub import WorkerConnection, is_worker_assignable

    conn = WorkerConnection(
        worker_id="w2",
        org_id="org",
        websocket=object(),  # type: ignore[arg-type]
        environment_status="degraded",
        capabilities={"chromium": False},
    )
    assert is_worker_assignable(conn, worker_pool="default") is False


def test_queue_reason_waiting_for_worker() -> None:
    from app.db.models import Workflow, WorkflowVersion

    with Session(engine) as session:
        org = org_svc.ensure_bootstrap(session)
        wf = Workflow(name="wf-queue", org_id=org.id)
        session.add(wf)
        session.flush()
        ver = WorkflowVersion(
            workflow_id=wf.id,
            version_index=1,
            nodes_json="[]",
            edges_json="[]",
            start_id="start",
            authored_by="test",
        )
        session.add(ver)
        session.flush()
        wf.current_version_id = ver.id
        session.add(wf)
        session.commit()
        run = run_svc.enqueue_run(
            wf.id,
            session,
            execution_mode="worker",
            worker_pool="default",
        )
        reason = run_svc.queue_reason(run.id)
    assert reason == "waiting_for_worker"


@pytest.mark.asyncio
async def test_abort_relay_sends_frame() -> None:
    from unittest.mock import AsyncMock

    sent: list[dict] = []

    async def fake_send(_worker_id: str, frame: dict) -> bool:
        sent.append(frame)
        return True

    worker_hub._run_to_worker["run-abort"] = "worker-1"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(worker_hub, "send_frame", fake_send)
        await worker_hub.request_abort_on_worker("run-abort")
    assert sent == [{"type": "abort", "run_id": "run-abort"}]


def test_llm_proxy_requires_worker_auth(client: TestClient) -> None:
    res = client.post(
        "/api/v1/internal/llm/complete",
        json={"purpose": "test", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert res.status_code == 401


def test_llm_proxy_rejects_invalid_worker_token(client: TestClient) -> None:
    res = client.post(
        "/api/v1/internal/llm/complete",
        json={"purpose": "test", "messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": "Bearer wk_sess_invalid"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_register_connection_marks_worker_online() -> None:
    from unittest.mock import AsyncMock

    email = f"online-{uuid.uuid4().hex[:8]}@example.com"
    with Session(engine) as session:
        user, org = _bootstrap_user(session, email, "pass")
        worker = Worker(
            machine_id=f"m-{uuid.uuid4().hex}",
            display_name="test-worker",
            hostname="host",
            user_id=user.id,
            org_id=org.id,
            status="offline",
            approval_status="approved",
            created_at=_utcnow(),
        )
        session.add(worker)
        session.commit()
        session.refresh(worker)
        worker_id = worker.id
        org_id = org.id

    ws = AsyncMock()
    await worker_hub.register_connection(
        worker_id,
        org_id,
        ws,
        environment={"environment_status": "ready", "capabilities": {"chromium": True}},
    )
    with Session(engine) as session:
        row = session.get(Worker, worker_id)
        assert row is not None
        assert row.status == "online"


def test_worker_login_pending_when_approval_required(client: TestClient) -> None:
    email = f"worker-{uuid.uuid4().hex[:8]}@example.com"
    password = "secret-pass"
    with Session(engine) as session:
        _user, org = _bootstrap_user(session, email, password)
        _set_org_policy(session, org.id, "approval_required")

    machine_id = f"machine-{uuid.uuid4().hex}"
    data = _worker_login(
        client, email=email, password=password, machine_id=machine_id
    )
    assert data["approval_status"] == "pending"
    assert data["desktop_client_policy"] == "approval_required"


def test_worker_login_auto_approved_when_open(client: TestClient) -> None:
    email = f"worker-{uuid.uuid4().hex[:8]}@example.com"
    password = "secret-pass"
    with Session(engine) as session:
        _user, org = _bootstrap_user(session, email, password)
        _set_org_policy(session, org.id, "open")

    machine_id = f"machine-{uuid.uuid4().hex}"
    data = _worker_login(
        client, email=email, password=password, machine_id=machine_id
    )
    assert data["approval_status"] == "approved"


def test_worker_login_disabled_policy_returns_403(client: TestClient) -> None:
    email = f"worker-{uuid.uuid4().hex[:8]}@example.com"
    password = "secret-pass"
    with Session(engine) as session:
        _user, org = _bootstrap_user(session, email, password)
        _set_org_policy(session, org.id, "disabled")

    res = client.post(
        "/api/v1/workers/login",
        json={
            "email": email,
            "password": password,
            "machine_id": f"machine-{uuid.uuid4().hex}",
            "hostname": "test-host",
        },
    )
    assert res.status_code == 403


def test_pending_worker_not_assignable() -> None:
    from app.services.worker_hub import WorkerConnection, is_worker_assignable

    conn = WorkerConnection(
        worker_id="w-pending",
        org_id="org",
        websocket=object(),  # type: ignore[arg-type]
        environment_status="ready",
        approval_status="pending",
    )
    assert is_worker_assignable(conn, worker_pool="default") is False


@pytest.mark.asyncio
async def test_approve_enables_dispatch(client: TestClient) -> None:
    from unittest.mock import AsyncMock, patch

    from app.db.models import Workflow, WorkflowVersion
    from app.schemas import Edge, Node, Workflow as WorkflowSchema

    email = f"worker-{uuid.uuid4().hex[:8]}@example.com"
    password = "secret-pass"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    with Session(engine) as session:
        user, org = _bootstrap_user(session, email, password)
        _bootstrap_user(session, admin_email, password, role="admin")
        _set_org_policy(session, org.id, "approval_required")
        org_id = org.id

    machine_id = f"machine-{uuid.uuid4().hex}"
    login = _worker_login(
        client, email=email, password=password, machine_id=machine_id
    )
    worker_id = login["worker_id"]
    token = login["worker_session_token"]

    wf_schema = WorkflowSchema(
        nodes=[
            Node(id="start", type="start", label="start"),
            Node(id="end", type="end", label="end"),
        ],
        edges=[Edge(id="e1", source="start", target="end")],
        start_id="start",
    )
    with Session(engine) as session:
        wf = Workflow(name="wf-approve", org_id=org_id)
        session.add(wf)
        session.flush()
        ver = WorkflowVersion(
            workflow_id=wf.id,
            version_index=1,
            nodes_json="[]",
            edges_json="[]",
            start_id="start",
            authored_by="test",
        )
        ver.nodes_json = __import__("json").dumps(wf_schema.model_dump()["nodes"])
        ver.edges_json = __import__("json").dumps(wf_schema.model_dump()["edges"])
        session.add(ver)
        session.flush()
        wf.current_version_id = ver.id
        session.add(wf)
        session.commit()
        run = run_svc.enqueue_run(
            wf.id,
            session,
            execution_mode="worker",
            worker_pool="default",
        )
        run_id = run.id

    ws = AsyncMock()
    await worker_hub.register_connection(
        worker_id,
        org_id,
        ws,
        environment={"environment_status": "ready", "capabilities": {"chromium": True}},
    )
    assert await worker_hub.try_assign_run(run_id) is False

    admin_token = _web_login(client, admin_email, password)
    approve = client.post(
        f"/api/workers/{worker_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert approve.status_code == 200, approve.text

    sent: list[dict] = []

    async def fake_send(_worker_id: str, frame: dict) -> bool:
        sent.append(frame)
        return True

    with patch.object(worker_hub, "send_frame", fake_send):
        assert await worker_hub.try_assign_run(run_id) is True
    assert sent and sent[0]["type"] == "execute_run"


def test_reject_revokes_worker_sessions(client: TestClient) -> None:
    email = f"worker-{uuid.uuid4().hex[:8]}@example.com"
    password = "secret-pass"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    with Session(engine) as session:
        _user, org = _bootstrap_user(session, email, password)
        _bootstrap_user(session, admin_email, password, role="admin")
        _set_org_policy(session, org.id, "approval_required")

    login = _worker_login(
        client,
        email=email,
        password=password,
        machine_id=f"machine-{uuid.uuid4().hex}",
    )
    worker_id = login["worker_id"]
    token = login["worker_session_token"]

    admin_token = _web_login(client, admin_email, password)
    reject = client.post(
        f"/api/workers/{worker_id}/reject",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert reject.status_code == 200, reject.text
    assert reject.json()["approval_status"] == "rejected"

    with Session(engine) as session:
        assert worker_session_svc.lookup_worker_by_token(session, token) is None


def test_non_admin_cannot_approve_worker(client: TestClient) -> None:
    email = f"worker-{uuid.uuid4().hex[:8]}@example.com"
    password = "secret-pass"
    member_email = f"member-{uuid.uuid4().hex[:8]}@example.com"
    with Session(engine) as session:
        _user, org = _bootstrap_user(session, email, password)
        _bootstrap_user(session, member_email, password, role="member")
        _set_org_policy(session, org.id, "approval_required")

    login = _worker_login(
        client,
        email=email,
        password=password,
        machine_id=f"machine-{uuid.uuid4().hex}",
    )
    worker_id = login["worker_id"]

    member_token = _web_login(client, member_email, password)
    res = client.post(
        f"/api/workers/{worker_id}/approve",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert res.status_code == 403


def test_cloud_execution_rejected_when_control_plane_only(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.db.models import Workflow, WorkflowVersion
    from app.settings import settings

    monkeypatch.setattr(settings, "execution_backend", "control_plane_only")
    email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    password = "secret-pass"
    with Session(engine) as session:
        _user, org = _bootstrap_user(session, email, password, role="admin")
        wf = Workflow(name="wf-cloud-block", org_id=org.id)
        session.add(wf)
        session.flush()
        ver = WorkflowVersion(
            workflow_id=wf.id,
            version_index=1,
            nodes_json="[]",
            edges_json="[]",
            start_id="start",
            authored_by="test",
        )
        session.add(ver)
        session.flush()
        wf.current_version_id = ver.id
        session.add(wf)
        session.commit()
        wf_id = wf.id

    token = _web_login(client, email, password)
    res = client.post(
        "/api/runs",
        json={"workflow_id": wf_id, "execution_mode": "cloud"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert "worker" in res.json()["detail"].lower()


def test_worker_oauth_login_with_session_token(client: TestClient) -> None:
    from app.auth.session import create_session_token

    email = f"oauth-worker-{uuid.uuid4().hex[:8]}@example.com"
    password = "secret-pass"
    with Session(engine) as session:
        user, _org = _bootstrap_user(session, email, password)
        user_id = user.id

    session_token = create_session_token(user_id)
    machine_id = f"machine-{uuid.uuid4().hex}"
    res = client.post(
        "/api/v1/workers/login/oauth",
        json={
            "session_token": session_token,
            "machine_id": machine_id,
            "hostname": "oauth-host",
            "environment": {
                "environment_status": "ready",
                "checks": [],
                "capabilities": {"platform": "Darwin", "agent_version": "0.1.0"},
            },
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["worker_session_token"]
    assert body["worker_id"]


def test_worker_oauth_login_with_exchange_code(client: TestClient) -> None:
    from app.services.oauth.exchange_store import issue_exchange_code, reset_exchange_store_for_tests

    reset_exchange_store_for_tests()
    email = f"oauth-worker-{uuid.uuid4().hex[:8]}@example.com"
    password = "secret-pass"
    with Session(engine) as session:
        user, _org = _bootstrap_user(session, email, password)
        code = issue_exchange_code(user_id=user.id)

    machine_id = f"machine-{uuid.uuid4().hex}"
    res = client.post(
        "/api/v1/workers/login/oauth",
        json={
            "oauth_exchange_code": code,
            "machine_id": machine_id,
            "hostname": "oauth-host",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["worker_session_token"]


def test_runtime_settings_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.settings import settings

    monkeypatch.setattr(settings, "execution_backend", "control_plane_only")
    res = client.get("/api/settings/runtime")
    assert res.status_code == 200
    body = res.json()
    assert body["execution_backend"] == "control_plane_only"
    assert body["worker_only"] is True

