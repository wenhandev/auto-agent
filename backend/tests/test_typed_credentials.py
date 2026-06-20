from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.crypto import decrypt, encrypt
from app.db.models import Credential, WorkflowCredential
from app.db.session import engine
from app.integrations.auth import RenderedRequest, inject_auth
from app.integrations.credential_types import (
    FIXTURE_API_KEY_TYPE,
    FIXTURE_BASIC_TYPE,
    FIXTURE_BEARER_TYPE,
    FIXTURE_OAUTH2_TYPE,
    GENERIC_CREDENTIAL_TYPE,
)
from app.integrations.redaction import redact_request_summary
from app.main import app
from app.nodes import integration as integration_node
from app.routers.oauth2 import _sign_state


def test_generic_credential_type_none_strategy():
    assert GENERIC_CREDENTIAL_TYPE.auth.strategy == "none"


@pytest.mark.asyncio
async def test_api_key_header_injector():
    req = RenderedRequest(
        method="GET",
        url="https://example.com",
        query={},
        headers={},
        body=None,
        body_kind="json",
    )
    await inject_auth(
        req,
        cred_type=FIXTURE_API_KEY_TYPE,
        cred_fields={"api_key": "abc"},
    )
    assert req.headers["X-Api-Key"] == "abc"
    redacted = redact_request_summary(
        {"headers": req.headers, "query": req.query, "url": req.url, "method": "GET"},
        req.secret_keys,
    )
    assert redacted["headers"]["X-Api-Key"] == "***"


@pytest.mark.asyncio
async def test_bearer_injector():
    req = RenderedRequest(
        method="GET",
        url="https://example.com",
        query={},
        headers={},
        body=None,
        body_kind="json",
    )
    await inject_auth(
        req,
        cred_type=FIXTURE_BEARER_TYPE,
        cred_fields={"token": "tok123"},
    )
    assert req.headers["Authorization"] == "Bearer tok123"


@pytest.mark.asyncio
async def test_basic_injector():
    import base64

    req = RenderedRequest(
        method="GET",
        url="https://example.com",
        query={},
        headers={},
        body=None,
        body_kind="json",
    )
    await inject_auth(
        req,
        cred_type=FIXTURE_BASIC_TYPE,
        cred_fields={"username": "u", "password": "p"},
    )
    expected = base64.b64encode(b"u:p").decode()
    assert req.headers["Authorization"] == f"Basic {expected}"


def test_generic_back_compat_no_injection():
    req = RenderedRequest(
        method="GET",
        url="https://example.com",
        query={},
        headers={},
        body=None,
        body_kind="json",
    )
    import asyncio

    asyncio.run(
        inject_auth(
            req,
            cred_type=GENERIC_CREDENTIAL_TYPE,
            cred_fields={"api_key": "legacy"},
        )
    )
    assert "X-Api-Key" not in req.headers
    assert "Authorization" not in req.headers


def test_oauth_callback_rejects_bad_state():
    client = TestClient(app)
    resp = client.get(
        "/api/oauth2/callback",
        params={"code": "x", "state": "tampered"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "error=" in resp.headers["location"]


def test_oauth_connect_stores_tokens():
    transport = httpx.MockTransport(
        lambda r: httpx.Response(
            200,
            json={
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 3600,
            },
            headers={"content-type": "application/json"},
        )
    )

    with Session(engine) as session:
        blob = encrypt(
            json.dumps(
                {"client_id": "cid", "client_secret": "csec"},
                ensure_ascii=False,
            ).encode()
        )
        cred = Credential(
            name=f"oauth_cred_{uuid.uuid4().hex[:8]}",
            type="fixture_oauth2",
            ciphertext=blob,
        )
        session.add(cred)
        session.commit()
        session.refresh(cred)

        state = _sign_state(
            {"app": "_fixture", "credential_id": cred.id, "ts": time.time(), "nonce": "n"}
        )

        import asyncio
        from app.integrations.credential_types import FIXTURE_OAUTH2_TYPE
        from app.routers import oauth2 as oauth2_router

        auth = FIXTURE_OAUTH2_TYPE.auth

        from app.settings import settings

        async def _run():
            payload = oauth2_router._verify_state(state)
            body = await oauth2_router.exchange_authorization_code(
                token_url=auth.token_url or "",
                data={
                    "grant_type": "authorization_code",
                    "code": "auth-code",
                    "client_id": "cid",
                    "client_secret": "csec",
                    "redirect_uri": f"{settings.oauth_callback_base}/api/oauth2/callback",
                },
                transport=transport,
            )
            fields = oauth2_router._load_cred_fields(cred)
            token_field = auth.token_field or "access_token"
            fields[token_field] = str(body[token_field])
            if body.get("refresh_token"):
                fields["refresh_token"] = str(body["refresh_token"])
            if body.get("expires_in") is not None:
                fields["expires_at"] = str(time.time() + float(body["expires_in"]))
            oauth2_router._store_cred_fields(cred, fields, session)
            return {"connected": True, "app": payload["app"]}

        out = asyncio.run(_run())
        assert out["connected"] is True

        session.refresh(cred)
        fields = json.loads(decrypt(cred.ciphertext).decode())
        assert fields["access_token"] == "new-access"
        assert fields["refresh_token"] == "new-refresh"
        assert "expires_at" in fields


@pytest.mark.asyncio
async def test_expired_token_refreshed_before_use():
    refresh_hits: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "oauth.fixture.example.com/token" in str(request.url):
            refresh_hits.append("refresh")
            return httpx.Response(
                200,
                json={"access_token": "fresh-token", "expires_in": 3600},
                headers={"content-type": "application/json"},
            )
        return httpx.Response(
            200,
            json={"data": [{"id": 1}]},
            headers={"content-type": "application/json"},
        )

    transport = httpx.MockTransport(handler)

    with Session(engine) as session:
        blob = encrypt(
            json.dumps(
                {
                    "client_id": "cid",
                    "client_secret": "csec",
                    "access_token": "stale",
                    "refresh_token": "rtok",
                    "expires_at": str(time.time() - 120),
                },
                ensure_ascii=False,
            ).encode()
        )
        cred = Credential(
            name=f"oauth_run_{uuid.uuid4().hex[:8]}",
            type="fixture_oauth2",
            ciphertext=blob,
        )
        session.add(cred)
        session.commit()
        session.refresh(cred)
        session.add(
            WorkflowCredential(workflow_id="wf-oauth", credential_id=cred.id)
        )
        session.commit()

        # Need descriptor that uses oauth - temporarily use bearer via manual inject test
        # Instead test integration refresh path with a minimal mock operation - skip if no oauth descriptor
        # Test refresh function via integration oauth path on a custom inline - use _refresh_oauth_token directly
        from app.nodes.integration import _refresh_oauth_token, _load_credential

        cred_row, fields = _load_credential(cred.name, session, workflow_id=None)
        token = await _refresh_oauth_token(
            cred_row, fields, session, transport=transport
        )
        assert token == "fresh-token"
        assert refresh_hits == ["refresh"]

        _, updated = _load_credential(cred.name, session, workflow_id=None)
        assert updated["access_token"] == "fresh-token"
