from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

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


def _make_session_cred(
    session: Session,
    *,
    name: str | None = None,
    cred_type: str = "fixture_api_key",
    fields: dict[str, str] | None = None,
    workflow_id: str = "wf-test",
) -> Credential:
    cred_name = name or f"fixture_key_{uuid.uuid4().hex[:8]}"
    blob = encrypt(json.dumps(fields or {"api_key": "secret-abc"}, ensure_ascii=False).encode())
    cred = Credential(name=cred_name, type=cred_type, ciphertext=blob)
    session.add(cred)
    session.commit()
    session.refresh(cred)
    session.add(
        WorkflowCredential(workflow_id=workflow_id, credential_id=cred.id)
    )
    session.commit()
    return cred, cred_name


@pytest.mark.asyncio
async def test_list_emits_one_item_per_record():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            200,
            json={"data": [{"id": 1}, {"id": 2}, {"id": 3}]},
            headers={"content-type": "application/json"},
        )

    transport = httpx.MockTransport(handler)
    with Session(engine) as session:
        cred, cred_name = _make_session_cred(session)
        result = await integration_node.run(
            {
                "app": "_fixture",
                "resource": "records",
                "operation": "list",
                "credential": cred_name,
                "fields": {"limit": 10},
            },
            input_items=[],
            context={},
            session=session,
            workflow_id="wf-test",
            transport=transport,
        )
    assert len(result.items) == 3
    assert result.items[0].json["id"] == 1


@pytest.mark.asyncio
async def test_get_emits_single_item():
    transport = httpx.MockTransport(
        lambda r: httpx.Response(
            200,
            json={"data": {"id": "x1", "name": "alpha"}},
            headers={"content-type": "application/json"},
        )
    )
    with Session(engine) as session:
        cred, cred_name = _make_session_cred(session)
        result = await integration_node.run(
            {
                "app": "_fixture",
                "resource": "records",
                "operation": "get",
                "credential": cred_name,
                "fields": {"id": "x1"},
            },
            input_items=[],
            context={},
            session=session,
            workflow_id="wf-test",
            transport=transport,
        )
    assert len(result.items) == 1
    assert result.items[0].json["id"] == "x1"


@pytest.mark.asyncio
async def test_missing_required_field():
    with Session(engine) as session:
        cred, cred_name = _make_session_cred(session)
        with pytest.raises(IntegrationError, match="missing required field 'id'"):
            await integration_node.run(
                {
                    "app": "_fixture",
                    "resource": "records",
                    "operation": "get",
                    "credential": cred_name,
                    "fields": {},
                },
                input_items=[],
                context={},
                session=session,
                workflow_id="wf-test",
            )


@pytest.mark.asyncio
async def test_http_500_maps_to_failure():
    transport = httpx.MockTransport(
        lambda r: httpx.Response(500, text="boom")
    )
    with Session(engine) as session:
        cred, cred_name = _make_session_cred(session)
        with pytest.raises(IntegrationError, match="HTTP 500"):
            await integration_node.run(
                {
                    "app": "_fixture",
                    "resource": "records",
                    "operation": "list",
                    "credential": cred_name,
                    "fields": {"limit": 5},
                },
                input_items=[],
                context={},
                session=session,
                workflow_id="wf-test",
                transport=transport,
            )


@pytest.mark.asyncio
async def test_two_page_cursor_pagination():
    state = {"page": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "cursor=page2" in str(request.url):
            return httpx.Response(
                200,
                json={"data": [{"id": 3}], "next_cursor": None},
                headers={"content-type": "application/json"},
            )
        return httpx.Response(
            200,
            json={
                "data": [{"id": 1}, {"id": 2}],
                "next_cursor": "page2",
            },
            headers={"content-type": "application/json"},
        )

    transport = httpx.MockTransport(handler)
    with Session(engine) as session:
        cred, cred_name = _make_session_cred(session)
        result = await integration_node.run(
            {
                "app": "_fixture",
                "resource": "records",
                "operation": "list",
                "credential": cred_name,
                "fields": {"limit": 10},
            },
            input_items=[],
            context={},
            session=session,
            workflow_id="wf-test",
            transport=transport,
        )
    assert len(result.items) == 3


@pytest.mark.asyncio
async def test_pagination_cap_truncation(monkeypatch):
    from app import settings as settings_mod

    monkeypatch.setattr(settings_mod.settings, "max_items_per_node", 2)

    pages = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        pages["n"] += 1
        if pages["n"] == 1:
            return httpx.Response(
                200,
                json={"data": [{"id": 1}, {"id": 2}], "next_cursor": "more"},
                headers={"content-type": "application/json"},
            )
        return httpx.Response(
            200,
            json={"data": [{"id": 3}], "next_cursor": None},
            headers={"content-type": "application/json"},
        )

    transport = httpx.MockTransport(handler)
    with Session(engine) as session:
        cred, cred_name = _make_session_cred(session)
        result = await integration_node.run(
            {
                "app": "_fixture",
                "resource": "records",
                "operation": "list",
                "credential": cred_name,
                "fields": {"limit": 10},
            },
            input_items=[],
            context={},
            session=session,
            workflow_id="wf-test",
            transport=transport,
        )
    assert len(result.items) == 2
    assert result.output.get("truncated") is True


@pytest.mark.asyncio
async def test_auth_header_redacted_in_output():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("X-Api-Key", "")
        return httpx.Response(
            200,
            json={"data": [{"id": 1}]},
            headers={"content-type": "application/json"},
        )

    transport = httpx.MockTransport(handler)
    with Session(engine) as session:
        cred, cred_name = _make_session_cred(session, fields={"api_key": "super-secret"})
        result = await integration_node.run(
            {
                "app": "_fixture",
                "resource": "records",
                "operation": "list",
                "credential": cred_name,
                "fields": {"limit": 1},
            },
            input_items=[],
            context={},
            session=session,
            workflow_id="wf-test",
            transport=transport,
        )
    assert captured["auth"] == "super-secret"
    req_summary = result.output["request"]
    assert req_summary["headers"]["X-Api-Key"] == "***"
