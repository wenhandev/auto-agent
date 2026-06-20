"""Recording session and workflow synthesis tests."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.agents.synthesizer import (
    _LOGIN_CREDENTIAL_PLACEHOLDER,
    _SYNTH_MARKER,
    synthesize_from_recording,
    trace_to_graph,
    validate_workflow_graph,
)
from app.db.models import ChatMessage, Recording, Workflow
from app.db.session import engine, init_db
from app.main import app
from app.services.recording import (
    append_event,
    is_sensitive_field,
    load_events,
    sanitize_fill_value,
    start_recording,
    stop_recording,
)


@pytest.fixture()
def client() -> TestClient:
    init_db()
    return TestClient(app)


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_trace_capture_fidelity() -> None:
    init_db()
    with Session(engine) as session:
        recording = await start_recording(
            session,
            name="fixture-trace",
            start_url="https://example.com",
            acquire_browser=False,
        )
        append_event(
            recording.id,
            {
                "type": "navigate",
                "url": "https://example.com",
                "description": "landing",
            },
        )
        append_event(
            recording.id,
            {
                "type": "click",
                "selector": "#submit",
                "description": "Submit button",
                "element_index": 3,
                "screenshot_ref": "shot-1",
            },
        )
        append_event(
            recording.id,
            {
                "type": "fill",
                "selector": "#q",
                "description": "search box",
                "value": "widgets",
            },
        )
        stopped = await stop_recording(session, recording.id, release_browser=False)

    events = load_events(stopped)
    assert len(events) == 3
    assert events[0]["type"] == "navigate"
    assert events[0]["url"] == "https://example.com"
    assert events[1]["selector"] == "#submit"
    assert events[1]["element_index"] == 3
    assert events[1]["screenshot_ref"] == "shot-1"
    assert events[2]["value"] == "widgets"


def test_sensitive_field_never_stored() -> None:
    assert is_sensitive_field(input_type="password")
    assert is_sensitive_field(autocomplete="one-time-code")
    assert is_sensitive_field(name="user_password")

    value, sensitive = sanitize_fill_value(
        "secret123",
        input_type="password",
        name="password",
    )
    assert sensitive is True
    assert value is None

    from app.services import recording as rec_svc

    rec_svc._active["tmp-recording"] = rec_svc._ActiveRecording("tmp-recording")
    try:
        event = append_event(
            "tmp-recording",
            {
                "type": "fill",
                "selector": "#pwd",
                "name": "password",
                "input_type": "password",
                "value": "secret123",
            },
        )
    finally:
        rec_svc._active.pop("tmp-recording", None)

    assert event["sensitive"] is True
    assert "value" not in event


def test_synthesis_produces_valid_workflow() -> None:
    events = [
        {
            "seq": 0,
            "type": "navigate",
            "url": "https://shop.example.com",
            "description": "open shop",
        },
        {
            "seq": 1,
            "type": "click",
            "selector": "#buy",
            "description": "Buy now",
        },
    ]
    graph = trace_to_graph(events)
    wf = validate_workflow_graph(graph)
    assert wf.start_id == "start"
    types = {n.type for n in wf.nodes}
    assert "navigate" in types
    assert "click" in types
    assert "end" in types


def test_parameter_inference_and_login_conversion() -> None:
    events = [
        {
            "seq": 0,
            "type": "navigate",
            "url": "https://app.example.com/login",
        },
        {
            "seq": 1,
            "type": "fill",
            "selector": "#email",
            "description": "email",
            "value": "user@example.com",
        },
        {
            "seq": 2,
            "type": "fill",
            "selector": "#password",
            "description": "password",
            "input_type": "password",
            "value": "should-not-appear",
            "sensitive": True,
        },
        {
            "seq": 3,
            "type": "fill",
            "description": "search box",
            "value": "hello world",
        },
    ]
    graph = trace_to_graph(events)
    login_nodes = [n for n in graph["nodes"] if n["type"] == "login"]
    assert len(login_nodes) == 1
    assert login_nodes[0]["params"]["credential"] == _LOGIN_CREDENTIAL_PLACEHOLDER

    fill_nodes = [n for n in graph["nodes"] if n["type"] == "fill"]
    assert any("{{params." in n["params"].get("value", "") for n in fill_nodes)
    param_names = {p["name"] for p in graph["parameters"]}
    assert "email" in param_names or "search_box" in param_names

    vision_nodes = [n for n in graph["nodes"] if n["type"] == "vision_act"]
    assert len(vision_nodes) >= 1


@pytest.mark.asyncio
async def test_generate_api_creates_draft_and_seeded_chat(client: TestClient) -> None:
    start = client.post(
        "/api/recordings",
        json={"name": _unique("api-rec"), "acquire_browser": False},
    )
    assert start.status_code == 200
    rec_id = start.json()["id"]

    ingest = client.post(
        f"/api/recordings/{rec_id}/events",
        json={
            "events": [
                {"type": "navigate", "url": "https://example.com"},
                {
                    "type": "click",
                    "selector": "#go",
                    "description": "Go",
                },
            ]
        },
    )
    assert ingest.status_code == 200
    assert len(ingest.json()) == 2

    stop = client.post(f"/api/recordings/{rec_id}/stop")
    assert stop.status_code == 200
    assert stop.json()["status"] == "stopped"
    assert stop.json()["event_count"] == 2

    gen = client.post(f"/api/recordings/{rec_id}/generate")
    assert gen.status_code == 200
    body = gen.json()
    assert body["workflow_id"]
    assert body["chat_session_id"]
    assert body["workflow"]["start_id"] == "start"

    with Session(engine) as session:
        wf = session.get(Workflow, body["workflow_id"])
        assert wf is not None
        assert wf.status == "draft"
        assert _SYNTH_MARKER in (wf.description or "")
        rec = session.get(Recording, rec_id)
        assert rec is not None
        assert rec.generated_workflow_id == body["workflow_id"]
        msgs = session.exec(
            select(ChatMessage).where(ChatMessage.session_id == body["chat_session_id"])
        ).all()
        assert any("我录制了这个流程" in m.content for m in msgs)


@pytest.mark.asyncio
async def test_synthesize_from_recording_persists_graph() -> None:
    from datetime import datetime, timezone

    init_db()
    with Session(engine) as session:
        now = datetime.now(timezone.utc)
        recording = Recording(
            name="stopped-rec",
            status="stopped",
            events_json=json.dumps(
                [
                    {"seq": 0, "type": "navigate", "url": "https://example.com"},
                ]
            ),
            created_at=now,
            started_at=now,
            stopped_at=now,
        )
        session.add(recording)
        session.commit()
        session.refresh(recording)

        wf_id, graph, chat_id = synthesize_from_recording(recording, session)
        assert wf_id
        assert graph["nodes"]
        assert chat_id

        refreshed = session.get(Recording, recording.id)
        assert refreshed is not None
        assert refreshed.status == "synthesized"
        assert refreshed.generated_workflow_json is not None
