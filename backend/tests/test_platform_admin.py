"""Platform admin bootstrap, authorization, and admin API tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.session import reset_login_rate_limiter_for_tests
from app.db.models import Organization, OrgMembership, User
from app.db.session import engine, init_db
from app.main import app
from app.services import orgs as org_svc
from app.settings import settings


@pytest.fixture(autouse=True)
def _fresh_auth(monkeypatch):
    init_db()
    reset_login_rate_limiter_for_tests()
    monkeypatch.setattr(settings, "admin_email", "platform-admin@test.local")
    monkeypatch.setattr(settings, "admin_password", "test-admin-pass")
    monkeypatch.setattr(settings, "oauth_password_login_enabled", True)
    monkeypatch.setattr(settings, "single_user_mode", False)
    monkeypatch.setattr(settings, "bootstrap_platform_admin", False)
    with Session(engine) as session:
        org_svc.ensure_bootstrap(session)
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _login(client: TestClient, email: str, password: str) -> None:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text


def test_bootstrap_platform_admin_grants_flag(monkeypatch, client: TestClient) -> None:
    monkeypatch.setattr(settings, "bootstrap_platform_admin", True)
    with Session(engine) as session:
        org_svc.ensure_bootstrap(session)

    _login(client, "platform-admin@test.local", "test-admin-pass")
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["is_platform_admin"] is True


def test_non_platform_admin_gets_403_on_admin_orgs(client: TestClient) -> None:
    with Session(engine) as session:
        org = session.exec(select(Organization)).first()
        assert org is not None
        user = User(
            email="regular@test.local",
            password_hash=org_svc.hash_password("regular-pass"),
            name="Regular",
        )
        session.add(user)
        session.flush()
        session.add(
            OrgMembership(user_id=user.id, org_id=org.id, role="member")
        )
        session.commit()

    _login(client, "regular@test.local", "regular-pass")
    resp = client.get("/api/admin/orgs")
    assert resp.status_code == 403


def test_platform_admin_lists_orgs_and_users(monkeypatch, client: TestClient) -> None:
    monkeypatch.setattr(settings, "bootstrap_platform_admin", True)
    with Session(engine) as session:
        org_svc.ensure_bootstrap(session)

    _login(client, "platform-admin@test.local", "test-admin-pass")

    orgs_resp = client.get("/api/admin/orgs")
    assert orgs_resp.status_code == 200
    org_items = orgs_resp.json()["items"]
    assert len(org_items) >= 1
    assert "name" in org_items[0]

    users_resp = client.get("/api/admin/users")
    assert users_resp.status_code == 200
    user_items = users_resp.json()["items"]
    assert any(u["email"] == "platform-admin@test.local" for u in user_items)
    admin_row = next(u for u in user_items if u["email"] == "platform-admin@test.local")
    assert admin_row["is_platform_admin"] is True
    assert len(admin_row["memberships"]) >= 1
