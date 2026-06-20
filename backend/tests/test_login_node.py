"""Login node executor tests with mocked browser and vision agent."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlmodel import Session

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app import executor
from app.agents.login import LoginAgent, _mask_field, _resolve_credential_value
from app.db.crypto import encrypt
from app.db.models import Credential, Workflow, WorkflowCredential, WorkflowVersion
from app.db.session import engine, init_db
from app.nodes import login as login_node
from app.schemas import Node
from app.services.credential_interpolation import CredentialResolutionError


async def _capture_emit() -> tuple[Any, list[dict]]:
    events: list[dict] = []

    async def emit(event: str, *, node_id: str | None = None, **extra: Any) -> None:
        payload = {"event": event, "node_id": node_id}
        payload.update(extra)
        events.append(payload)

    return emit, events


def _seed_workflow(session: Session) -> str:
    wf = Workflow(name=f"login-wf-{uuid.uuid4().hex[:8]}")
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
    workflow_id: str | None = None,
    link: bool = True,
) -> Credential:
    blob = encrypt(json.dumps(fields, ensure_ascii=False).encode())
    cred = Credential(name=name, type="generic", ciphertext=blob)
    session.add(cred)
    session.commit()
    session.refresh(cred)
    if link and workflow_id:
        session.add(
            WorkflowCredential(workflow_id=workflow_id, credential_id=cred.id)
        )
        session.commit()
    return cred


@pytest.fixture()
def mock_page(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    page = MagicMock()
    page.url = "https://example.com/login"
    page.title = AsyncMock(return_value="Login")
    page.goto = AsyncMock()
    page.locator = MagicMock(return_value=MagicMock())
    pw_locator = page.locator.return_value
    pw_locator.count = AsyncMock(return_value=1)
    pw_locator.inner_text = AsyncMock(return_value="Sign in")
    monkeypatch.setattr(login_node, "get_page", AsyncMock(return_value=page))
    monkeypatch.setattr(
        login_node.browser_tools, "get_active_profile_id", lambda: None
    )
    return page


@pytest.mark.asyncio
async def test_executor_login_emits_events(
    monkeypatch: pytest.MonkeyPatch,
    mock_page: MagicMock,
) -> None:
    init_db()
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        cred_name = f"site-login-{uuid.uuid4().hex[:6]}"
        _make_cred(
            session,
            name=cred_name,
            fields={"username": "alice", "password": "s3cret!"},
            workflow_id=wf_id,
        )

        async def fake_run_login(self, **kwargs):
            on_step = kwargs.get("on_step")
            if on_step:
                await on_step(
                    {
                        "step_index": 1,
                        "thought": "submit",
                        "action": "click_element",
                        "target_index": 3,
                        "screenshot_ref": "/tmp/login.png",
                    }
                )
            mock_page.url = "https://example.com/dashboard"
            pw = mock_page.locator.return_value
            pw.count = AsyncMock(return_value=0)
            return {"completed": True, "summary": "logged in", "steps": 2}

        monkeypatch.setattr(LoginAgent, "run_login", fake_run_login)

        emit, events = await _capture_emit()
        node = Node(
            id="lg1",
            type="login",
            label="登录",
            params={"credential": cred_name, "url": "https://example.com/login"},
        )
        result = await executor._run_node(
            node, emit, session=session, workflow_id=wf_id
        )

        assert result["logged_in"] is True
        assert result["method"] == "vision"
        assert events[0]["event"] == "login_started"
        assert events[-1]["event"] == "login_completed"
        assert events[-1]["credential"] == cred_name
        assert "s3cret" not in json.dumps(events)
        vision_steps = [e for e in events if e["event"] == "vision_step"]
        assert len(vision_steps) == 1


@pytest.mark.asyncio
async def test_fill_credential_masks_secrets_in_tool_response() -> None:
    fields = {"username": "alice", "password": "hunter2"}
    assert _resolve_credential_value(fields, "username") == "alice"
    assert _resolve_credential_value(fields, "password") == "hunter2"
    masked = _mask_field("my-cred", "password")
    assert masked == "<password for my-cred>"
    assert "hunter2" not in masked


@pytest.mark.asyncio
async def test_unlinked_credential_rejected(mock_page: MagicMock) -> None:
    init_db()
    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        other_wf = _seed_workflow(session)
        cred_name = f"unlinked-{uuid.uuid4().hex[:6]}"
        _make_cred(
            session,
            name=cred_name,
            fields={"username": "bob", "password": "x"},
            workflow_id=other_wf,
            link=True,
        )

        emit, events = await _capture_emit()
        with pytest.raises(login_node.LoginError, match="not linked"):
            await login_node.run(
                {"credential": cred_name},
                node_id="lg2",
                emit=emit,
                session=session,
                workflow_id=wf_id,
            )

        failed = [e for e in events if e["event"] == "login_failed"]
        assert len(failed) == 1
        assert "not linked" in failed[0]["reason"]
        assert "x" not in json.dumps(failed)


@pytest.mark.asyncio
async def test_profile_short_circuit(
    monkeypatch: pytest.MonkeyPatch,
    mock_page: MagicMock,
) -> None:
    init_db()
    monkeypatch.setattr(
        login_node.browser_tools, "get_active_profile_id", lambda: "prof-1"
    )
    mock_page.url = "https://example.com/app"
    pw = mock_page.locator.return_value
    pw.count = AsyncMock(return_value=0)

    with Session(engine) as session:
        wf_id = _seed_workflow(session)
        cred_name = f"profile-cred-{uuid.uuid4().hex[:6]}"
        _make_cred(
            session,
            name=cred_name,
            fields={"username": "carol", "password": "pw"},
            workflow_id=wf_id,
        )

        emit, events = await _capture_emit()
        result = await login_node.run(
            {"credential": cred_name},
            node_id="lg3",
            emit=emit,
            session=session,
            workflow_id=wf_id,
        )

        assert result["logged_in"] is True
        assert result["method"] == "profile"
        assert result["steps"] == 0
        completed = [e for e in events if e["event"] == "login_completed"]
        assert completed[0]["method"] == "profile"
        started = [e for e in events if e["event"] == "login_started"]
        assert len(started) == 1


@pytest.mark.asyncio
async def test_login_params_schema_validation() -> None:
    from app.schemas import LoginParams

    p = LoginParams.model_validate(
        {
            "credential": "my-login",
            "url": "https://example.com",
            "success_criteria": "url:/dashboard",
            "totp_identifier": "my-2fa",
        }
    )
    assert p.credential == "my-login"
    assert p.totp_identifier == "my-2fa"

    with pytest.raises(Exception):
        LoginParams.model_validate({"url": "https://example.com"})


@pytest.mark.asyncio
async def test_verify_success_criteria_url(mock_page: MagicMock) -> None:
    mock_page.url = "https://example.com/dashboard"
    pw = mock_page.locator.return_value
    pw.count = AsyncMock(return_value=0)
    ok, reason = await login_node.verify_login_success(
        mock_page,
        success_criteria="url:/dashboard",
        start_url="https://example.com/login",
    )
    assert ok is True
    assert reason == "success_criteria_url"


@pytest.mark.asyncio
async def test_totp_current_code_rfc_vector() -> None:
    import base64

    from app.services.totp import current_code

    # RFC 6238 Appendix B — store ASCII secret as base32 (our vault format)
    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    assert current_code(secret, for_time=59) == "287082"
    assert current_code(secret, for_time=1111111109) == "081804"
    assert current_code(secret, for_time=1111111111) == "050471"


@pytest.mark.asyncio
async def test_progress_messages_never_contain_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keyless stub progress messages must not echo credential secrets."""
    captured_progress: list[str] = []

    async def on_progress(msg: str) -> None:
        captured_progress.append(msg)

    secret_password = "super-secret-pw-99"
    fields = {"username": "user1", "password": secret_password}

    monkeypatch.setattr("app.agents.login.llm_is_configured", lambda: False)

    agent = LoginAgent()
    await agent.run_login(
        credential_name="test-cred",
        credential_fields=fields,
        session=None,
        workflow_id=None,
        on_progress=on_progress,
    )

    joined = " ".join(captured_progress)
    assert secret_password not in joined
