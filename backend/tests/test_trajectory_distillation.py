"""Trajectory distillation and route skill proposal tests."""

from __future__ import annotations

import json
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

from app.agents.synthesizer import synthesize_from_recording
from app.db.models import Recording, RouteSkill, RouteSkillProposal, Run, RunEvent, Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.main import app
from app.services.recording import append_event, start_recording, stop_recording
from app.services.route_skill_proposals import adopt_proposal, dismiss_proposal
from app.services.trajectory_distillation import (
    atomize_events,
    classify_capability,
    distill_recording,
    distill_segment_prompt,
    events_from_task_run,
    merge_route_prompts,
)


@pytest.fixture()
def client() -> TestClient:
    init_db()
    return TestClient(app)


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _sample_events() -> list[dict]:
    return [
        {"type": "navigate", "url": "https://example.com/login", "description": "login page"},
        {"type": "fill", "url": "https://example.com/login", "description": "email", "sensitive": True},
        {"type": "navigate", "url": "https://example.com/search?q=phone", "description": "search page"},
        {"type": "fill", "url": "https://example.com/search?q=phone", "description": "query", "value": "iphone"},
        {"type": "click", "url": "https://example.com/search?q=phone", "description": "Search button"},
        {"type": "scroll"},
    ]


def test_atomize_splits_by_url_pattern() -> None:
    segments = atomize_events(_sample_events())
    assert len(segments) >= 2
    patterns = {segment.url_pattern for segment in segments}
    assert len(patterns) >= 2


def test_classify_login_and_search() -> None:
    events = _sample_events()
    login_events = [events[0], events[1]]
    search_events = [events[2], events[3], events[4]]
    assert classify_capability(login_events) == "login-with-credentials"
    assert classify_capability(search_events) == "search-and-select"


def test_distill_segment_prompt_omits_secrets() -> None:
    segment_events = [
        {"type": "fill", "description": "password", "sensitive": True},
    ]
    from app.services.trajectory_distillation import TraceSegment

    segment = TraceSegment(
        domain="example.com",
        url_pattern="https://example.com/login",
        capability="login-with-credentials",
        events=tuple(segment_events),
    )
    prompt = distill_segment_prompt(segment)
    assert "credentials" in prompt.lower()
    assert "password" not in prompt.lower() or "Enter credentials" in prompt


def test_merge_route_prompts() -> None:
    merged = merge_route_prompts("step one", "step two")
    assert "step one" in merged
    assert "step two" in merged


@pytest.mark.asyncio
async def test_distill_recording_persists_proposals() -> None:
    init_db()
    with Session(engine) as session:
        recording = await start_recording(
            session,
            name=_unique("distill"),
            start_url="https://example.com/login",
            acquire_browser=False,
        )
        for event in _sample_events():
            append_event(recording.id, event)
        recording = await stop_recording(session, recording.id)
        result = distill_recording(recording, session)
        assert result.proposals
        assert result.workflow_graph.get("nodes")
        pending = session.exec(
            select(RouteSkillProposal).where(
                RouteSkillProposal.source_id == recording.id,
                RouteSkillProposal.status == "pending",
            )
        ).all()
        assert len(pending) == len(result.proposals)


@pytest.mark.asyncio
async def test_adopt_creates_disabled_route_skill() -> None:
    init_db()
    with Session(engine) as session:
        recording = await start_recording(
            session,
            name=_unique("adopt"),
            acquire_browser=False,
        )
        append_event(recording.id, _sample_events()[0])
        recording = await stop_recording(session, recording.id)
        result = distill_recording(recording, session)
        proposal = result.proposals[0]
        _, skill = adopt_proposal(session, proposal.id)
        assert skill.enabled is False
        assert skill.url_pattern == proposal.url_pattern


@pytest.mark.asyncio
async def test_adopt_merges_existing_route_skill() -> None:
    init_db()
    pattern = f"https://merge-{uuid.uuid4().hex[:8]}.example.com/login"
    with Session(engine) as session:
        existing = RouteSkill(
            scope="global",
            url_pattern=pattern,
            prompt="existing guidance",
            enabled=True,
        )
        session.add(existing)
        session.commit()
        session.refresh(existing)

        recording = await start_recording(
            session,
            name=_unique("merge"),
            acquire_browser=False,
        )
        append_event(
            recording.id,
            {"type": "navigate", "url": pattern, "description": "login"},
        )
        recording = await stop_recording(session, recording.id)
        proposal = distill_recording(recording, session).proposals[0]
        _, skill = adopt_proposal(session, proposal.id)
        assert skill.id == existing.id
        assert "existing guidance" in skill.prompt
        assert proposal.prompt.splitlines()[0] in skill.prompt


@pytest.mark.asyncio
async def test_dismiss_proposal() -> None:
    init_db()
    with Session(engine) as session:
        recording = await start_recording(
            session,
            name=_unique("dismiss"),
            acquire_browser=False,
        )
        append_event(recording.id, _sample_events()[0])
        recording = await stop_recording(session, recording.id)
        proposal = distill_recording(recording, session).proposals[0]
        dismissed = dismiss_proposal(session, proposal.id)
        assert dismissed.status == "dismissed"


@pytest.mark.asyncio
async def test_generate_api_returns_proposals(client: TestClient) -> None:
    init_db()
    with Session(engine) as session:
        recording = await start_recording(
            session,
            name=_unique("api-gen"),
            acquire_browser=False,
        )
        for event in _sample_events():
            append_event(recording.id, event)
        recording = await stop_recording(session, recording.id)
        recording_id = recording.id

    res = client.post(f"/api/recordings/{recording_id}/generate")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["workflow_id"]
    assert len(body["route_skill_proposals"]) >= 1


@pytest.mark.asyncio
async def test_distill_api(client: TestClient) -> None:
    init_db()
    with Session(engine) as session:
        recording = await start_recording(
            session,
            name=_unique("api-distill"),
            acquire_browser=False,
        )
        append_event(recording.id, _sample_events()[0])
        recording = await stop_recording(session, recording.id)
        recording_id = recording.id

    res = client.post(f"/api/recordings/{recording_id}/distill", json={"use_llm": False})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["distill_mode"] == "rule"
    assert body["route_skill_proposals"]


@pytest.mark.asyncio
async def test_synthesize_from_recording_returns_proposals() -> None:
    init_db()
    with Session(engine) as session:
        recording = await start_recording(
            session,
            name=_unique("synth"),
            acquire_browser=False,
        )
        for event in _sample_events():
            append_event(recording.id, event)
        recording = await stop_recording(session, recording.id)
        wf_id, graph, chat_id, proposals = synthesize_from_recording(recording, session)
        assert wf_id
        assert graph["nodes"]
        assert chat_id
        assert proposals

        proposal_ids = [p.id for p in proposals]
        for pid in proposal_ids:
            session.delete(session.get(RouteSkillProposal, pid))
        wf = session.get(type(recording), recording.id)
        from app.db.models import Workflow

        workflow = session.get(Workflow, wf_id)
        if workflow:
            session.delete(workflow)
        session.delete(recording)
        session.commit()


def _seed_completed_task_run(session: Session) -> str:
    wf = Workflow(name=_unique("wf"))
    session.add(wf)
    session.commit()
    session.refresh(wf)
    ver = WorkflowVersion(
        workflow_id=wf.id,
        version_index=1,
        nodes_json="[]",
        edges_json="[]",
        start_id="start",
        authored_by="manual",
    )
    session.add(ver)
    session.commit()
    session.refresh(ver)
    wf.current_version_id = ver.id
    session.add(wf)
    now = datetime.now(timezone.utc)
    run = Run(
        workflow_id=wf.id,
        workflow_version_id=ver.id,
        status="completed",
        mode="autonomous",
        objective="search phones",
        start_url="https://example.com/search",
        result_json=json.dumps(
            {"success": True, "summary": "ok", "steps_taken": 2, "items": []}
        ),
        queued_at=now,
        started_at=now,
        finished_at=now,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    session.add(
        RunEvent(
            run_id=run.id,
            seq=0,
            event_type="vision_step",
            payload_json=json.dumps(
                {
                    "event": "vision_step",
                    "action": "click_element",
                    "thought": "Click search",
                    "url": "https://example.com/search",
                },
                ensure_ascii=False,
            ),
        )
    )
    session.commit()
    return run.id


def test_events_from_task_run_maps_vision_steps() -> None:
    payloads = [
        {
            "event": "vision_step",
            "action": "click_element",
            "thought": "Click search",
            "url": "https://example.com/search",
        },
        {
            "event": "vision_step",
            "action": "type_text",
            "thought": "Type query",
            "url": "https://example.com/search",
            "args": {"text": "iphone"},
        },
    ]
    events = events_from_task_run(
        start_url="https://example.com",
        payloads=payloads,
    )
    assert events[0]["type"] == "navigate"
    assert any(event["type"] == "click" for event in events)
    assert any(event["type"] == "fill" for event in events)


def test_distill_task_run_api(client: TestClient) -> None:
    init_db()
    with Session(engine) as session:
        run_id = _seed_completed_task_run(session)

    res = client.post(f"/api/tasks/{run_id}/distill-route-skills")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["run_id"] == run_id
    assert len(body["route_skill_proposals"]) >= 1


def test_distill_task_run_rejects_failed_run(client: TestClient) -> None:
    init_db()
    with Session(engine) as session:
        run_id = _seed_completed_task_run(session)
        run = session.get(Run, run_id)
        assert run is not None
        run.result_json = json.dumps(
            {"success": False, "summary": "failed", "steps_taken": 1, "items": []}
        )
        session.add(run)
        session.commit()

    res = client.post(f"/api/tasks/{run_id}/distill-route-skills")
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_adopt_preview_merge(client: TestClient) -> None:
    init_db()
    pattern = f"https://preview-{uuid.uuid4().hex[:8]}.example.com/app"
    with Session(engine) as session:
        skill = RouteSkill(
            scope="global",
            url_pattern=pattern,
            prompt="existing",
            enabled=True,
        )
        session.add(skill)
        session.commit()

    with Session(engine) as session:
        recording = await start_recording(
            session, name=_unique("preview"), acquire_browser=False
        )
        append_event(
            recording.id,
            {"type": "navigate", "url": pattern, "description": "go"},
        )
        recording = await stop_recording(session, recording.id)
        proposal = distill_recording(recording, session).proposals[0]

    res = client.get(f"/api/route-skill-proposals/{proposal.id}/adopt-preview")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["will_create_new"] is False
    assert "existing" in body["merged_prompt"]


def test_route_skill_buckets_api(client: TestClient) -> None:
    init_db()
    with Session(engine) as session:
        session.add(
            RouteSkill(
                scope="global",
                url_pattern=f"https://bucket-{uuid.uuid4().hex[:6]}.example.com/",
                prompt="hello",
                enabled=False,
            )
        )
        session.commit()

    res = client.get("/api/route-skills/buckets")
    assert res.status_code == 200, res.text
    assert isinstance(res.json(), list)
    assert len(res.json()) >= 1
