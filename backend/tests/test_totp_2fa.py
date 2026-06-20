"""TOTP 2FA automation: RFC vectors, interpolation, masking, login integration."""

from __future__ import annotations

import base64
import json
import sys
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.agents.login import LoginAgent
from app.db.crypto import encrypt
from app.db.models import Credential, Workflow, WorkflowCredential, WorkflowVersion
from app.db.session import engine
from app.integrations.credential_types import (
    CREDIT_CARD_CREDENTIAL_TYPE,
    TOTP_CREDENTIAL_TYPE,
)
from app.main import app
from app.nodes import login as login_node
from app.services.credential_masking import mask_card_number, mask_field
from app.services.totp import (
    REFRESH_WINDOW_SECONDS,
    SKEW_STEPS,
    codes_with_skew,
    current_code,
    resolve_totp_code,
    seconds_until_rollover,
    should_refresh_code,
)
from app.services.credential_interpolation import CredentialResolutionError
from app.services.variable_interpolation import (
    VariableResolutionError,
    resolve_params,
)


def _seed_workflow(session: Session) -> str:
    wf = Workflow(name=f"totp-wf-{uuid.uuid4().hex[:8]}")
    session.add(wf)
    session.commit()
    session.refresh(wf)
    version = WorkflowVersion(
        workflow_id=wf.id,
        version_index=1,
        nodes_json="[]",
        edges_json="[]",
        start_id="s",
        authored_by="manual",
    )
    session.add(version)
    session.commit()
    session.refresh(version)
    wf.current_version_id = version.id
    session.add(wf)
    session.commit()
    return wf.id


def _make_cred(
    session: Session,
    *,
    name: str,
    fields: dict[str, str],
    cred_type: str = "generic",
    workflow_id: str | None = None,
    link: bool = True,
) -> Credential:
    blob = encrypt(json.dumps(fields, ensure_ascii=False).encode())
    cred = Credential(name=name, type=cred_type, ciphertext=blob)
    session.add(cred)
    session.commit()
    session.refresh(cred)
    if link and workflow_id:
        session.add(
            WorkflowCredential(workflow_id=workflow_id, credential_id=cred.id)
        )
        session.commit()
    return cred


def test_rfc6238_appendix_b_vectors() -> None:
    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    assert current_code(secret, for_time=59) == "287082"
    assert current_code(secret, for_time=1111111109) == "081804"
    assert current_code(secret, for_time=1111111111) == "050471"


def test_default_totp_params() -> None:
    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    assert current_code(secret, for_time=59, digits=6, period=30) == "287082"


def test_codes_with_skew_includes_neighbors() -> None:
    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    codes = codes_with_skew(secret, for_time=1111111111, skew_steps=SKEW_STEPS)
    assert len(codes) >= 2
    assert "050471" in codes


def test_refresh_window_constants() -> None:
    assert REFRESH_WINDOW_SECONDS == 5
    assert seconds_until_rollover(for_time=28, period=30) == 2
    assert should_refresh_code(for_time=28, period=30) is True
    assert should_refresh_code(for_time=10, period=30) is False


def test_totp_and_card_credential_types_registered() -> None:
    assert TOTP_CREDENTIAL_TYPE.type == "totp"
    assert any(f.name == "totp_secret" for f in TOTP_CREDENTIAL_TYPE.fields)
    assert CREDIT_CARD_CREDENTIAL_TYPE.type == "credit_card"
    assert any(f.name == "number" for f in CREDIT_CARD_CREDENTIAL_TYPE.fields)


def test_mask_totp_secret_never_plaintext() -> None:
    secret = "JBSWY3DPEHPK3PXP"
    masked = mask_field("totp_secret", secret, credential_type="totp")
    assert masked == "***"
    assert secret not in masked


def test_mask_card_number_last_four() -> None:
    assert mask_card_number("4111111111111111") == "**** **** **** 1111"
    assert mask_field("number", "4111111111111111", credential_type="credit_card") == (
        "**** **** **** 1111"
    )
    assert mask_field("cvc", "123", credential_type="credit_card") == "***"


def test_credential_api_masks_totp_secret() -> None:
    client = TestClient(app)
    name = f"totp-api-{uuid.uuid4().hex[:6]}"
    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    resp = client.post(
        "/api/credentials",
        json={
            "name": name,
            "type": "totp",
            "fields": {"totp_secret": secret, "digits": "6", "period": "30"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "totp"
    fields = {f["name"]: f["masked_value"] for f in body["fields"]}
    assert fields["totp_secret"] == "***"
    assert secret not in json.dumps(body)


def test_totp_token_resolves_live_code() -> None:
    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        name = f"my-2fa-{uuid.uuid4().hex[:6]}"
        _make_cred(
            session,
            name=name,
            fields={"totp_secret": secret},
            cred_type="totp",
            workflow_id=wf_id,
        )
        out = resolve_params(
            {"code": "{{totp." + name + "}}"},
            session=session,
            workflow_id=wf_id,
        )
        assert out["code"] == current_code(secret)


def test_unlinked_totp_token_rejected() -> None:
    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        other_wf = _seed_workflow(session)
        name = f"unlinked-totp-{uuid.uuid4().hex[:6]}"
        _make_cred(
            session,
            name=name,
            fields={"totp_secret": secret},
            cred_type="totp",
            workflow_id=other_wf,
        )
        with pytest.raises((VariableResolutionError, CredentialResolutionError), match="not linked"):
            resolve_params(
                {"code": "{{totp." + name + "}}"},
                session=session,
                workflow_id=wf_id,
            )


def test_card_token_resolves_field() -> None:
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        name = f"my-visa-{uuid.uuid4().hex[:6]}"
        _make_cred(
            session,
            name=name,
            fields={
                "number": "4111111111111111",
                "exp_month": "12",
                "exp_year": "2030",
                "cvc": "999",
            },
            cred_type="credit_card",
            workflow_id=wf_id,
        )
        out = resolve_params(
            {"pan": "{{card." + name + ".number}}"},
            session=session,
            workflow_id=wf_id,
        )
        assert out["pan"] == "4111111111111111"


def test_resolve_totp_code_from_linked_credential() -> None:
    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        name = f"resolve-{uuid.uuid4().hex[:6]}"
        _make_cred(
            session,
            name=name,
            fields={"totp_secret": secret},
            cred_type="totp",
            workflow_id=wf_id,
        )
        code = resolve_totp_code(
            name, session, workflow_id=wf_id, refresh_if_stale=False
        )
        assert code == current_code(secret)


def test_post_run_accepts_totp_identifier() -> None:
    client = TestClient(app)
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
    resp = client.post(
        f"/api/workflows/{wf_id}/runs",
        json={"totp_identifier": "my-2fa-cred"},
    )
    assert resp.status_code == 200
    assert resp.json()["totp_identifier"] == "my-2fa-cred"


@pytest.mark.asyncio
async def test_login_get_totp_code_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    expected = current_code(secret)

    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        totp_name = f"login-totp-{uuid.uuid4().hex[:6]}"
        _make_cred(
            session,
            name=totp_name,
            fields={"totp_secret": secret},
            cred_type="totp",
            workflow_id=wf_id,
        )

        captured: list[str] = []

        async def fake_run_login(self, **kwargs):
            from app.services.totp import resolve_totp_code as rtc

            code = rtc(totp_name, session, workflow_id=wf_id, refresh_if_stale=False)
            captured.append(code)
            page.url = "https://example.com/dashboard"
            return {"completed": True, "summary": "logged in", "steps": 1}

        monkeypatch.setattr(LoginAgent, "run_login", fake_run_login)
        monkeypatch.setattr(
            login_node.browser_tools, "get_active_profile_id", lambda: None
        )
        page = MagicMock()
        page.url = "https://example.com/login"
        monkeypatch.setattr(login_node, "get_page", AsyncMock(return_value=page))
        pw = page.locator.return_value
        pw.count = AsyncMock(return_value=0)

        cred_name = f"site-{uuid.uuid4().hex[:6]}"
        _make_cred(
            session,
            name=cred_name,
            fields={"username": "alice", "password": "pw"},
            workflow_id=wf_id,
        )

        events: list[dict[str, Any]] = []

        async def emit(event: str, **extra: Any) -> None:
            events.append({"event": event, **extra})

        result = await login_node.run(
            {"credential": cred_name, "totp_identifier": totp_name},
            node_id="lg-totp",
            emit=emit,
            session=session,
            workflow_id=wf_id,
        )

        assert result["logged_in"] is True
        assert captured == [expected]
        assert expected not in json.dumps(events)
