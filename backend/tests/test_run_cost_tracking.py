"""Tests for per-run cost tracking and aggregation."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.models import Run, Workflow, WorkflowVersion
from app.db.session import engine
from app.main import app
from app.services import artifact_context
from app.services import cost_tracking as cost_svc
from app.services import runs as run_svc


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def seeded_run() -> str:
    run_id = str(uuid.uuid4())
    wf_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    with Session(engine) as session:
        session.add(
            Workflow(
                id=wf_id,
                name="cost-test",
                current_version_id=version_id,
            )
        )
        session.add(
            WorkflowVersion(
                id=version_id,
                workflow_id=wf_id,
                version_index=1,
                nodes_json="[]",
                edges_json="[]",
                start_id="start",
                authored_by="manual",
            )
        )
        session.add(
            Run(
                id=run_id,
                workflow_id=wf_id,
                workflow_version_id=version_id,
                status="completed",
                queued_at=_utcnow(),
            )
        )
        session.commit()
    return run_id


def test_cost_hint_accumulates_on_event(seeded_run: str) -> None:
    run_svc.persist_and_fanout(
        seeded_run,
        1,
        {
            "event": "node_self_healed",
            "node_id": "click-1",
            "cost_hint": {
                "input_tokens": 120,
                "output_tokens": 15,
                "vision_calls": 1,
                "model": "gpt-4o",
            },
        },
    )
    run_svc.persist_and_fanout(
        seeded_run,
        2,
        {
            "event": "node_self_healed",
            "node_id": "click-2",
            "cost_hint": {
                "input_tokens": 80,
                "output_tokens": 5,
                "vision_calls": 0,
                "model": "gpt-4o",
            },
        },
    )

    with Session(engine) as session:
        row = session.get(Run, seeded_run)
        assert row is not None
        assert row.total_input_tokens == 200
        assert row.total_output_tokens == 20
        assert row.total_llm_calls == 2
        assert row.total_vision_calls == 1
        assert row.estimated_cost_usd is not None
        assert row.estimated_cost_usd > 0
        node_costs = json.loads(row.node_cost_json or "{}")
        assert node_costs["click-1"]["input_tokens"] == 120
        assert node_costs["click-2"]["input_tokens"] == 80


def test_unknown_model_null_cost(seeded_run: str) -> None:
    run_svc.persist_and_fanout(
        seeded_run,
        1,
        {
            "event": "node_self_healed",
            "node_id": "n1",
            "cost_hint": {
                "input_tokens": 1000,
                "output_tokens": 200,
                "vision_calls": 0,
                "model": "totally-unknown-model",
            },
        },
    )
    with Session(engine) as session:
        row = session.get(Run, seeded_run)
        assert row is not None
        assert row.total_input_tokens == 1000
        assert row.total_output_tokens == 200
        assert row.estimated_cost_usd is None
        assert row.cost_note == cost_svc.UNKNOWN_PRICE_NOTE


def test_trace_takes_precedence_over_hint(seeded_run: str) -> None:
    run_svc.persist_and_fanout(
        seeded_run,
        1,
        {
            "event": "llm_call_completed",
            "node_id": "prompt-1",
            "llm_trace": {
                "call_id": "call-abc",
                "model": "gpt-4o",
                "input_tokens": 300,
                "output_tokens": 40,
            },
            "cost_hint": {
                "call_id": "call-abc",
                "input_tokens": 999,
                "output_tokens": 999,
                "vision_calls": 0,
                "model": "gpt-4o",
            },
        },
    )
    with Session(engine) as session:
        row = session.get(Run, seeded_run)
        assert row is not None
        assert row.total_input_tokens == 300
        assert row.total_output_tokens == 40


@pytest.mark.asyncio
async def test_text_prompt_records_mocked_llm_usage(
    monkeypatch: pytest.MonkeyPatch,
    seeded_run: str,
) -> None:
    from app.nodes import text_prompt

    artifact_context.set_run_context(seeded_run, node_id="tp-1")

    usage = MagicMock()
    usage.prompt_token_count = 150
    usage.candidates_token_count = 25
    response = MagicMock()
    response.text = '{"answer": "ok"}'
    response.usage_metadata = usage

    async def fake_generate_content(**_: Any) -> MagicMock:
        return response

    client = MagicMock()
    client.aio.models.generate_content = fake_generate_content
    monkeypatch.setattr(text_prompt, "llm_is_configured", lambda: True)
    monkeypatch.setattr("app.agents.model.get_genai_client", lambda: client)
    monkeypatch.setattr("app.agents.model.get_genai_model_id", lambda: "gpt-4o")

    items = await text_prompt.run(
        {"prompt": "hello"},
        input_items=[],
        context={},
    )
    assert items[0].json["answer"] == "ok"

    with Session(engine) as session:
        row = session.get(Run, seeded_run)
        assert row is not None
        assert row.total_input_tokens == 150
        assert row.total_output_tokens == 25
        assert row.total_llm_calls == 1
        node_costs = json.loads(row.node_cost_json or "{}")
        assert node_costs["tp-1"]["input_tokens"] == 150


def test_subworkflow_rollup(seeded_run: str) -> None:
    child_id = str(uuid.uuid4())
    with Session(engine) as session:
        parent = session.get(Run, seeded_run)
        assert parent is not None
        child = Run(
            id=child_id,
            workflow_id=parent.workflow_id,
            workflow_version_id=parent.workflow_version_id,
            status="completed",
            queued_at=_utcnow(),
            parent_run_id=seeded_run,
            total_input_tokens=500,
            total_output_tokens=50,
            total_llm_calls=2,
            total_vision_calls=1,
            usage_summary_json=json.dumps(
                {
                    "models": {
                        "gpt-4o": {
                            "input_tokens": 500,
                            "output_tokens": 50,
                            "llm_calls": 2,
                        }
                    },
                    "processed_call_ids": [],
                }
            ),
        )
        session.add(child)
        session.commit()

    cost_svc.rollup_child_to_parent(
        parent_run_id=seeded_run,
        child_run_id=child_id,
        parent_node_id="subwf-1",
    )

    with Session(engine) as session:
        parent = session.get(Run, seeded_run)
        assert parent is not None
        assert parent.total_input_tokens == 500
        assert parent.total_output_tokens == 50
        assert parent.total_llm_calls == 2
        assert parent.total_vision_calls == 1
        node_costs = json.loads(parent.node_cost_json or "{}")
        assert node_costs["subwf-1"]["child_run_id"] == child_id


def test_window_cost_summary_api(client: TestClient, seeded_run: str) -> None:
    run_svc.persist_and_fanout(
        seeded_run,
        1,
        {
            "event": "node_self_healed",
            "node_id": "n1",
            "cost_hint": {
                "input_tokens": 1000,
                "output_tokens": 100,
                "vision_calls": 0,
                "model": "gpt-4o",
            },
        },
    )
    start = quote((_utcnow() - timedelta(days=1)).isoformat())
    end = quote((_utcnow() + timedelta(days=1)).isoformat())
    resp = client.get(f"/api/runs/cost-summary?from={start}&to={end}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_runs"] >= 1
    assert body["total_input_tokens"] >= 1000
    assert body["estimated_cost_usd"] is not None


def test_list_runs_sort_by_cost(client: TestClient) -> None:
    wf_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    cheap_id = str(uuid.uuid4())
    pricey_id = str(uuid.uuid4())
    now = _utcnow()
    with Session(engine) as session:
        session.add(
            Workflow(
                id=wf_id,
                name="sort-cost",
                current_version_id=version_id,
            )
        )
        session.add(
            WorkflowVersion(
                id=version_id,
                workflow_id=wf_id,
                version_index=1,
                nodes_json="[]",
                edges_json="[]",
                start_id="start",
                authored_by="manual",
            )
        )
        session.add(
            Run(
                id=cheap_id,
                workflow_id=wf_id,
                workflow_version_id=version_id,
                status="completed",
                queued_at=now,
                estimated_cost_usd=0.001,
            )
        )
        session.add(
            Run(
                id=pricey_id,
                workflow_id=wf_id,
                workflow_version_id=version_id,
                status="completed",
                queued_at=now - timedelta(minutes=1),
                estimated_cost_usd=0.05,
            )
        )
        session.commit()

    resp = client.get("/api/runs", params={"workflow_id": wf_id, "sort": "cost"})
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()]
    assert ids.index(pricey_id) < ids.index(cheap_id)


def test_get_run_exposes_cost_fields(client: TestClient, seeded_run: str) -> None:
    run_svc.persist_and_fanout(
        seeded_run,
        1,
        {
            "event": "node_self_healed",
            "node_id": "n1",
            "cost_hint": {
                "input_tokens": 42,
                "output_tokens": 7,
                "vision_calls": 0,
                "model": "gpt-4o",
            },
        },
    )
    resp = client.get(f"/api/runs/{seeded_run}")
    assert resp.status_code == 200
    run = resp.json()["run"]
    assert run["total_input_tokens"] == 42
    assert run["total_output_tokens"] == 7
    assert run["estimated_cost_usd"] is not None
    assert run["usage_summary"]["models"]["gpt-4o"]["input_tokens"] == 42
    assert run["node_costs"][0]["node_id"] == "n1"
