from __future__ import annotations

import base64
import json
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.crypto import encrypt
from app.db.models import Credential, WorkflowCredential
from app.db.session import engine
from app.integrations import load_integrations
from app.nodes import integration as integration_node
from app.nodes.integration import IntegrationError
from sqlmodel import Session


@pytest.fixture(autouse=True)
def _fresh_registry():
    load_integrations()
    yield


def _load_fixture(app: str, name: str) -> dict[str, Any]:
    path = (
        _BACKEND_ROOT
        / "app"
        / "integrations"
        / app
        / "fixtures"
        / "responses.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    return data[name]


def _make_oauth_cred(
    session: Session,
    *,
    cred_type: str,
    token: str = "test-access-token",
    workflow_id: str = "wf-test",
) -> tuple[Credential, str]:
    cred_name = f"{cred_type}_{uuid.uuid4().hex[:8]}"
    fields = {
        "client_id": "test-client",
        "client_secret": "test-secret",
        "access_token": token,
    }
    blob = encrypt(json.dumps(fields, ensure_ascii=False).encode())
    cred = Credential(name=cred_name, type=cred_type, ciphertext=blob)
    session.add(cred)
    session.commit()
    session.refresh(cred)
    session.add(WorkflowCredential(workflow_id=workflow_id, credential_id=cred.id))
    session.commit()
    return cred, cred_name


def _make_bearer_cred(
    session: Session,
    *,
    cred_type: str,
    token: str,
    workflow_id: str = "wf-test",
) -> tuple[Credential, str]:
    cred_name = f"{cred_type}_{uuid.uuid4().hex[:8]}"
    fields = {"token": token}
    blob = encrypt(json.dumps(fields, ensure_ascii=False).encode())
    cred = Credential(name=cred_name, type=cred_type, ciphertext=blob)
    session.add(cred)
    session.commit()
    session.refresh(cred)
    session.add(WorkflowCredential(workflow_id=workflow_id, credential_id=cred.id))
    session.commit()
    return cred, cred_name


def _response_from_fixture(spec: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        spec["status"],
        json=spec.get("json"),
        headers=spec.get("headers", {}),
    )


@pytest.mark.asyncio
async def test_slack_post_message_emits_message_item():
    fx = _load_fixture("slack", "postMessage_success")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == "Bearer test-access-token"
        body = json.loads(request.content.decode())
        assert body["channel"] == "C123"
        assert body["text"] == "hello"
        return _response_from_fixture(fx)

    with Session(engine) as session:
        _, cred_name = _make_oauth_cred(session, cred_type="slack_oauth2")
        result = await integration_node.run(
            {
                "app": "slack",
                "resource": "chat",
                "operation": "postMessage",
                "credential": cred_name,
                "fields": {"channel": "C123", "text": "hello"},
            },
            input_items=[],
            context={},
            session=session,
            workflow_id="wf-test",
            transport=httpx.MockTransport(handler),
        )
    assert len(result.items) == 1
    assert result.items[0].json["text"] == "hello"


@pytest.mark.asyncio
async def test_slack_ok_false_fails_node():
    fx = _load_fixture("slack", "postMessage_channel_not_found")
    transport = httpx.MockTransport(lambda r: _response_from_fixture(fx))
    with Session(engine) as session:
        _, cred_name = _make_oauth_cred(session, cred_type="slack_oauth2")
        with pytest.raises(IntegrationError, match="channel_not_found"):
            await integration_node.run(
                {
                    "app": "slack",
                    "resource": "chat",
                    "operation": "postMessage",
                    "credential": cred_name,
                    "fields": {"channel": "C999", "text": "nope"},
                },
                input_items=[],
                context={},
                session=session,
                workflow_id="wf-test",
                transport=transport,
            )


@pytest.mark.asyncio
async def test_slack_conversations_list_paginates():
    page1 = _load_fixture("slack", "conversations_list_page1")
    page2 = _load_fixture("slack", "conversations_list_page2")
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.content.decode())
        body = json.loads(request.content.decode()) if request.content else {}
        if body.get("cursor") == "cursor-page-2":
            return _response_from_fixture(page2)
        return _response_from_fixture(page1)

    with Session(engine) as session:
        _, cred_name = _make_oauth_cred(session, cred_type="slack_oauth2")
        result = await integration_node.run(
            {
                "app": "slack",
                "resource": "conversations",
                "operation": "list",
                "credential": cred_name,
                "fields": {"limit": 100},
            },
            input_items=[],
            context={},
            session=session,
            workflow_id="wf-test",
            transport=httpx.MockTransport(handler),
        )
    assert len(result.items) == 3
    assert [i.json["name"] for i in result.items] == ["general", "ops", "random"]
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_gmail_send_builds_mime_and_emits_item():
    fx = _load_fixture("gmail", "send_success")
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return _response_from_fixture(fx)

    with Session(engine) as session:
        _, cred_name = _make_oauth_cred(session, cred_type="gmail_oauth2")
        result = await integration_node.run(
            {
                "app": "gmail",
                "resource": "messages",
                "operation": "send",
                "credential": cred_name,
                "fields": {
                    "to": "user@example.com",
                    "subject": "Hi",
                    "body": "Hello there",
                },
            },
            input_items=[],
            context={},
            session=session,
            workflow_id="wf-test",
            transport=httpx.MockTransport(handler),
        )
    raw = captured["body"]["raw"]
    padded = raw + "=" * (-len(raw) % 4)
    mime = base64.urlsafe_b64decode(padded.encode()).decode()
    assert "user@example.com" in mime
    assert "Subject: Hi" in mime
    assert "Hello there" in mime
    assert len(result.items) == 1
    assert result.items[0].json["id"] == "msg-abc123"


@pytest.mark.asyncio
async def test_gmail_list_paginates():
    page1 = _load_fixture("gmail", "list_page1")
    page2 = _load_fixture("gmail", "list_page2")
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        if "pageToken=page-2" in str(request.url):
            return _response_from_fixture(page2)
        return _response_from_fixture(page1)

    with Session(engine) as session:
        _, cred_name = _make_oauth_cred(session, cred_type="gmail_oauth2")
        result = await integration_node.run(
            {
                "app": "gmail",
                "resource": "messages",
                "operation": "list",
                "credential": cred_name,
                "fields": {"maxResults": 100, "q": ""},
            },
            input_items=[],
            context={},
            session=session,
            workflow_id="wf-test",
            transport=httpx.MockTransport(handler),
        )
    assert len(result.items) == 3
    assert len(urls) == 2


@pytest.mark.asyncio
async def test_gmail_get_single_message():
    fx = _load_fixture("gmail", "get_message")
    transport = httpx.MockTransport(lambda r: _response_from_fixture(fx))
    with Session(engine) as session:
        _, cred_name = _make_oauth_cred(session, cred_type="gmail_oauth2")
        result = await integration_node.run(
            {
                "app": "gmail",
                "resource": "messages",
                "operation": "get",
                "credential": cred_name,
                "fields": {"id": "m1", "format": "full"},
            },
            input_items=[],
            context={},
            session=session,
            workflow_id="wf-test",
            transport=transport,
        )
    assert len(result.items) == 1
    assert result.items[0].json["snippet"] == "Hello world"


@pytest.mark.asyncio
async def test_sheets_append_emits_update_summary():
    fx = _load_fixture("google_sheets", "append_success")

    def handler(request: httpx.Request) -> httpx.Response:
        assert "values/Data" in str(request.url) and ":append" in str(request.url)
        body = json.loads(request.content.decode())
        assert body["values"] == [["x", "1"], ["y", "2"]]
        return _response_from_fixture(fx)

    with Session(engine) as session:
        _, cred_name = _make_oauth_cred(session, cred_type="google_sheets_oauth2")
        result = await integration_node.run(
            {
                "app": "google_sheets",
                "resource": "values",
                "operation": "append",
                "credential": cred_name,
                "fields": {
                    "spreadsheet_id": "sheet-123",
                    "sheet": "Data",
                    "range": "A1",
                    "values": [["x", "1"], ["y", "2"]],
                },
            },
            input_items=[],
            context={},
            session=session,
            workflow_id="wf-test",
            transport=httpx.MockTransport(handler),
        )
    assert len(result.items) == 1
    assert result.items[0].json["updatedRows"] == 2


@pytest.mark.asyncio
async def test_sheets_get_as_objects():
    fx = _load_fixture("google_sheets", "get_matrix")
    transport = httpx.MockTransport(lambda r: _response_from_fixture(fx))
    with Session(engine) as session:
        _, cred_name = _make_oauth_cred(session, cred_type="google_sheets_oauth2")
        result = await integration_node.run(
            {
                "app": "google_sheets",
                "resource": "values",
                "operation": "get",
                "credential": cred_name,
                "fields": {
                    "spreadsheet_id": "sheet-123",
                    "sheet": "Data",
                    "range": "A1:B3",
                    "as_objects": True,
                },
            },
            input_items=[],
            context={},
            session=session,
            workflow_id="wf-test",
            transport=transport,
        )
    assert len(result.items) == 2
    assert result.items[0].json == {"name": "a", "age": "1"}
    assert result.items[1].json == {"name": "b", "age": "2"}


@pytest.mark.asyncio
async def test_sheets_get_raw_matrix():
    fx = _load_fixture("google_sheets", "get_matrix")
    transport = httpx.MockTransport(lambda r: _response_from_fixture(fx))
    with Session(engine) as session:
        _, cred_name = _make_oauth_cred(session, cred_type="google_sheets_oauth2")
        result = await integration_node.run(
            {
                "app": "google_sheets",
                "resource": "values",
                "operation": "get",
                "credential": cred_name,
                "fields": {
                    "spreadsheet_id": "sheet-123",
                    "sheet": "Data",
                    "range": "A1:B3",
                    "as_objects": False,
                },
            },
            input_items=[],
            context={},
            session=session,
            workflow_id="wf-test",
            transport=transport,
        )
    assert len(result.items) == 1
    assert result.items[0].json["values"][0] == ["name", "age"]


@pytest.mark.asyncio
async def test_notion_create_page_emits_page():
    fx = _load_fixture("notion", "create_page_success")
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["version"] = request.headers.get("Notion-Version", "")
        captured["auth"] = request.headers.get("Authorization", "")
        return _response_from_fixture(fx)

    with Session(engine) as session:
        _, cred_name = _make_bearer_cred(
            session, cred_type="notion_internal_token", token="secret_notion_token"
        )
        result = await integration_node.run(
            {
                "app": "notion",
                "resource": "pages",
                "operation": "create",
                "credential": cred_name,
                "fields": {
                    "parent": {"database_id": "db-123"},
                    "properties": {},
                    "children": [],
                },
            },
            input_items=[],
            context={},
            session=session,
            workflow_id="wf-test",
            transport=httpx.MockTransport(handler),
        )
    assert captured["version"] == "2022-06-28"
    assert captured["auth"] == "Bearer secret_notion_token"
    assert len(result.items) == 1
    assert result.items[0].json["id"] == "page-abc"


@pytest.mark.asyncio
async def test_notion_database_query_paginates():
    page1 = _load_fixture("notion", "database_query_page1")
    page2 = _load_fixture("notion", "database_query_page2")
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else {}
        bodies.append(body)
        if body.get("start_cursor") == "cursor-2":
            return _response_from_fixture(page2)
        return _response_from_fixture(page1)

    with Session(engine) as session:
        _, cred_name = _make_bearer_cred(
            session, cred_type="notion_internal_token", token="secret_notion_token"
        )
        result = await integration_node.run(
            {
                "app": "notion",
                "resource": "databases",
                "operation": "query",
                "credential": cred_name,
                "fields": {
                    "database_id": "db-123",
                    "filter": {},
                    "sorts": [],
                    "page_size": 100,
                },
            },
            input_items=[],
            context={},
            session=session,
            workflow_id="wf-test",
            transport=httpx.MockTransport(handler),
        )
    assert len(result.items) == 3
    assert len(bodies) == 2
    assert bodies[1]["start_cursor"] == "cursor-2"


def test_all_core_apps_registered():
    reg = load_integrations()
    for app in ("slack", "gmail", "google_sheets", "notion"):
        assert app in reg
