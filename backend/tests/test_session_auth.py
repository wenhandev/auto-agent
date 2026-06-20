"""Session login, role checks, workflow visibility, and cross-org auth."""

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
from app.db.models import ApiKey, Organization, OrgMembership, User, Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.main import app
from app.services import api_keys as api_key_svc
from app.services import orgs as org_svc
from app.settings import settings


@pytest.fixture(autouse=True)
def _fresh_auth_state():
    init_db()
    reset_rate_limiter_for_tests()
    reset_login_rate_limiter_for_tests()
    with Session(engine) as session:
        for row in session.exec(select(ApiKey)).all():
            session.delete(row)
        session.commit()
    yield
    reset_rate_limiter_for_tests()
    reset_login_rate_limiter_for_tests()


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


def _create_user(
    session: Session,
    email: str,
    password: str,
    *,
    org_id: str,
    role: str,
) -> User:
    user = User(
        email=email,
        password_hash=org_svc.hash_password(password),
        name=email.split("@")[0],
        created_at=_utcnow(),
    )
    session.add(user)
    session.flush()
    session.add(
        OrgMembership(
            user_id=user.id,
            org_id=org_id,
            role=role,
            created_at=_utcnow(),
        )
    )
    session.commit()
    session.refresh(user)
    return user


def _seed_workflow(
    session: Session,
    org_id: str,
    *,
    created_by: str | None = None,
    visibility: str = "org",
) -> str:
    wf = Workflow(
        name=f"wf-{uuid.uuid4().hex[:6]}",
        org_id=org_id,
        created_by=created_by,
        visibility=visibility,
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


def _login(client: TestClient, email: str, password: str) -> dict:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_login_logout_me_flow(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    password = "test-admin-pass"
    monkeypatch.setattr(settings, "admin_password", password)
    with Session(engine) as session:
        org = org_svc.ensure_bootstrap(session)
        email = settings.admin_email.strip().lower()
        admin = session.exec(select(User).where(User.email == email)).first()
        assert admin is not None
        admin.password_hash = org_svc.hash_password(password)
        session.add(admin)
        session.commit()
        org_id = org.id

    login = _login(client, email, password)
    assert login["token"]
    assert login["user"]["email"] == email
    assert login["user"]["current_org_id"] == org_id
    assert login["user"]["role"] == "owner"

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {login['token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == email

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_login_invalid_credentials(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401


def test_login_rate_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    password = "rate-limit-pass"
    monkeypatch.setattr(settings, "admin_password", password)
    email = settings.admin_email.strip().lower()
    with Session(engine) as session:
        admin = session.exec(select(User).where(User.email == email)).first()
        if admin is not None:
            admin.password_hash = org_svc.hash_password(password)
            session.add(admin)
            session.commit()
    for _ in range(11):
        resp = client.post(
            "/api/auth/login",
            json={"email": email, "password": "wrong-password"},
        )
    assert resp.status_code == 429


def test_viewer_cannot_delete_workflow(client: TestClient) -> None:
    password = "viewer-pass"
    with Session(engine) as session:
        org = org_svc.ensure_bootstrap(session)
        viewer = _create_user(
            session,
            f"viewer-{uuid.uuid4().hex[:6]}@example.com",
            password,
            org_id=org.id,
            role="viewer",
        )
        viewer_email = viewer.email
        wf_id = _seed_workflow(session, org.id)

    login = _login(client, viewer_email, password)
    resp = client.delete(
        f"/api/workflows/{wf_id}",
        headers={"Authorization": f"Bearer {login['token']}"},
    )
    assert resp.status_code == 403


def test_member_can_delete_workflow(client: TestClient) -> None:
    password = "member-pass"
    with Session(engine) as session:
        org = org_svc.ensure_bootstrap(session)
        member = _create_user(
            session,
            f"member-{uuid.uuid4().hex[:6]}@example.com",
            password,
            org_id=org.id,
            role="member",
        )
        member_email = member.email
        wf_id = _seed_workflow(session, org.id)

    login = _login(client, member_email, password)
    resp = client.delete(
        f"/api/workflows/{wf_id}",
        headers={"Authorization": f"Bearer {login['token']}"},
    )
    assert resp.status_code == 200


def test_member_cannot_manage_keys(client: TestClient) -> None:
    password = "member-key-pass"
    with Session(engine) as session:
        org = org_svc.ensure_bootstrap(session)
        member = _create_user(
            session,
            f"member-{uuid.uuid4().hex[:6]}@example.com",
            password,
            org_id=org.id,
            role="member",
        )
        member_email = member.email
        _, admin_key = api_key_svc.create_api_key(session, name="admin-key", org_id=org.id)

    member_login = _login(client, member_email, password)
    resp = client.post(
        "/api/v1/keys",
        headers={"Authorization": f"Bearer {member_login['token']}"},
        json={"name": "should-fail"},
    )
    assert resp.status_code == 403

    client.cookies.clear()
    resp_admin = client.post(
        "/api/v1/keys",
        headers={"Authorization": f"Bearer {admin_key}"},
        json={"name": "api-created"},
    )
    assert resp_admin.status_code == 201


def test_member_cannot_invite_members(client: TestClient) -> None:
    password = "member-invite-pass"
    with Session(engine) as session:
        org = org_svc.ensure_bootstrap(session)
        member = _create_user(
            session,
            f"member-{uuid.uuid4().hex[:6]}@example.com",
            password,
            org_id=org.id,
            role="member",
        )
        member_email = member.email
        org_id = org.id

    login = _login(client, member_email, password)
    resp = client.post(
        f"/api/orgs/{org_id}/members",
        headers={"Authorization": f"Bearer {login['token']}"},
        json={
            "email": f"new-{uuid.uuid4().hex[:6]}@example.com",
            "role": "viewer",
            "password": "long-enough-password",
        },
    )
    assert resp.status_code == 403


def test_admin_can_invite_member(client: TestClient) -> None:
    password = "admin-invite-pass"
    with Session(engine) as session:
        org = org_svc.ensure_bootstrap(session)
        admin = _create_user(
            session,
            f"admin-{uuid.uuid4().hex[:6]}@example.com",
            password,
            org_id=org.id,
            role="admin",
        )
        admin_email = admin.email
        org_id = org.id

    login = _login(client, admin_email, password)
    new_email = f"invited-{uuid.uuid4().hex[:6]}@example.com"
    resp = client.post(
        f"/api/orgs/{org_id}/members",
        headers={"Authorization": f"Bearer {login['token']}"},
        json={
            "email": new_email,
            "role": "viewer",
            "password": "long-enough-password",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == new_email


def test_private_workflow_visibility_filtering(client: TestClient) -> None:
    owner_password = "owner-pass"
    other_password = "other-pass"
    with Session(engine) as session:
        org = _create_org(session, f"vis-org-{uuid.uuid4().hex[:6]}")
        owner = _create_user(
            session,
            f"owner-{uuid.uuid4().hex[:6]}@example.com",
            owner_password,
            org_id=org.id,
            role="member",
        )
        other = _create_user(
            session,
            f"other-{uuid.uuid4().hex[:6]}@example.com",
            other_password,
            org_id=org.id,
            role="member",
        )
        owner_email = owner.email
        other_email = other.email
        org_id = org.id
        public_id = _seed_workflow(session, org.id, visibility="org")
        private_id = _seed_workflow(
            session, org.id, created_by=owner.id, visibility="private"
        )

    owner_login = _login(client, owner_email, owner_password)
    other_login = _login(client, other_email, other_password)

    owner_list = client.get(
        "/api/workflows",
        headers={
            "Authorization": f"Bearer {owner_login['token']}",
            "x-org-id": org_id,
        },
    ).json()
    owner_ids = {row["id"] for row in owner_list}
    assert public_id in owner_ids
    assert private_id in owner_ids

    other_list = client.get(
        "/api/workflows",
        headers={
            "Authorization": f"Bearer {other_login['token']}",
            "x-org-id": org_id,
        },
    ).json()
    other_ids = {row["id"] for row in other_list}
    assert public_id in other_ids
    assert private_id not in other_ids

    assert (
        client.get(
            f"/api/workflows/{private_id}",
            headers={
                "Authorization": f"Bearer {other_login['token']}",
                "x-org-id": org_id,
            },
        ).status_code
        == 404
    )


def test_session_cross_org_returns_404(client: TestClient) -> None:
    password = "cross-org-pass"
    with Session(engine) as session:
        org_a = org_svc.ensure_bootstrap(session)
        org_b = _create_org(session, f"org-b-{uuid.uuid4().hex[:6]}")
        user = _create_user(
            session,
            f"user-{uuid.uuid4().hex[:6]}@example.com",
            password,
            org_id=org_a.id,
            role="member",
        )
        user_email = user.email
        org_b_id = org_b.id
        wf_b = _seed_workflow(session, org_b.id)

    login = _login(client, user_email, password)
    resp = client.get(
        f"/api/workflows/{wf_b}",
        headers={
            "Authorization": f"Bearer {login['token']}",
            "x-org-id": org_b_id,
        },
    )
    assert resp.status_code == 404


def test_single_user_mode_auto_auth(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "single_user_mode", True)
    password = "single-user-pass"
    monkeypatch.setattr(settings, "admin_password", password)
    with Session(engine) as session:
        org = org_svc.ensure_bootstrap(session)
        org_id = org.id
        email = settings.admin_email.strip().lower()
        admin = session.exec(select(User).where(User.email == email)).first()
        if admin is not None:
            admin.password_hash = org_svc.hash_password(password)
            session.add(admin)
            session.commit()

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == settings.admin_email.strip().lower()
    assert body["current_org_id"] == org_id
    assert body["role"] == "owner"
