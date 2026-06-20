"""Google OAuth login tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.session import reset_login_rate_limiter_for_tests
from app.db.models import OrgMembership, User, UserIdentity
from app.db.session import engine, init_db
from app.main import app
from app.services.oauth.exchange_store import issue_exchange_code, reset_exchange_store_for_tests
from app.services.oauth.state_cookie import pack_oauth_state_cookie
from app.services import orgs as org_svc
from app.settings import settings


@pytest.fixture(autouse=True)
def _fresh_oauth_state(monkeypatch):
    init_db()
    reset_login_rate_limiter_for_tests()
    reset_exchange_store_for_tests()
    monkeypatch.setattr(settings, "oauth_google_client_id", "google-client-id")
    monkeypatch.setattr(settings, "oauth_google_client_secret", "google-client-secret")
    monkeypatch.setattr(settings, "oauth_callback_base", "http://testserver")
    monkeypatch.setattr(settings, "frontend_base_url", "http://frontend.test")
    monkeypatch.setattr(settings, "oauth_password_login_enabled", True)
    monkeypatch.setattr(settings, "oauth_signup_policy", "existing_users_only")
    yield
    reset_exchange_store_for_tests()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_oauth_providers_lists_google(client: TestClient) -> None:
    resp = client.get("/api/auth/oauth/providers")
    assert resp.status_code == 200
    body = resp.json()
    assert body["providers"] == ["google"]
    assert body["password_login_enabled"] is True


def test_oauth_start_redirects_to_google(client: TestClient) -> None:
    resp = client.get("/api/auth/oauth/google/start", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert "client_id=google-client-id" in location
    assert "code_challenge=" in location
    assert resp.cookies.get("auto_agent_oauth_state")


def test_oauth_exchange_issues_session(client: TestClient) -> None:
    with Session(engine) as session:
        org = org_svc.ensure_bootstrap(session)
        user = User(email="oauth@test.com", password_hash=None, name="OAuth User")
        session.add(user)
        session.flush()
        session.add(
            OrgMembership(user_id=user.id, org_id=org.id, role="owner")
        )
        session.commit()
        code = issue_exchange_code(user_id=user.id)

    resp = client.post("/api/auth/oauth/exchange", json={"code": code})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == "oauth@test.com"
    assert resp.cookies.get("session_token")


def test_oauth_callback_links_existing_user(client: TestClient) -> None:
    state = "test-state-token"
    verifier = "test-verifier-token"
    cookie = pack_oauth_state_cookie(
        secret=settings.session_secret,
        provider="google",
        state=state,
        code_verifier=verifier,
    )
    with Session(engine) as session:
        org = org_svc.ensure_bootstrap(session)
        user = User(
            email="admin@wenhandev.com",
            password_hash=org_svc.hash_password("secret"),
            name="Admin",
        )
        session.add(user)
        session.flush()
        session.add(OrgMembership(user_id=user.id, org_id=org.id, role="owner"))
        session.commit()

    async def fake_exchange(**kwargs):
        return {"access_token": "google-access-token"}

    async def fake_profile(**kwargs):
        from app.services.oauth.providers import OAuthProfile

        return OAuthProfile(subject_id="google-subject-123", email="admin@wenhandev.com")

    with (
        patch(
            "app.routers.oauth_login.oauth_providers.exchange_code_for_tokens",
            new=AsyncMock(side_effect=fake_exchange),
        ),
        patch(
            "app.routers.oauth_login.oauth_providers.fetch_user_profile",
            new=AsyncMock(side_effect=fake_profile),
        ),
    ):
        resp = client.get(
            "/api/auth/oauth/google/callback?code=abc&state=test-state-token",
            cookies={"auto_agent_oauth_state": cookie},
            follow_redirects=False,
        )

    assert resp.status_code == 302
    assert resp.headers["location"].startswith("http://frontend.test/login/oauth/callback?code=")

    with Session(engine) as session:
        identity = session.exec(
            select(UserIdentity).where(UserIdentity.provider_subject_id == "google-subject-123")
        ).first()
        assert identity is not None
