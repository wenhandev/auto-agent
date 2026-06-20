"""LLM trace artifact persistence and credential masking tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.models import Run, Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.main import app
from app.services import artifact_context
from app.services import artifacts as artifact_svc
from app.services import llm_traces as trace_svc


@pytest.fixture()
def artifact_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "artifacts"
    artifact_svc.set_artifact_root(root)
    artifact_svc.reset_seq_counters()
    monkeypatch.setattr("app.settings.settings.max_artifact_bytes", 1024 * 1024)
    yield root
    artifact_svc.reset_artifact_root()
    artifact_svc.reset_seq_counters()
    artifact_context.clear_run_context()


@pytest.fixture()
def seeded_run(artifact_tmp: Path) -> str:
    init_db()
    with Session(engine) as session:
        wf = Workflow(name="llm-trace-test-wf")
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
        run = Run(
            workflow_id=wf.id,
            workflow_version_id=version.id,
            status="completed",
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return run.id


def test_mask_trace_never_leaks_secrets() -> None:
    secret = "SuperSecretPassword123!"
    artifact_context.register_sensitive("password", secret)
    payload = trace_svc.build_trace_payload(
        model="gpt-4o",
        system=f"Login with password {secret}",
        messages=[{"role": "user", "content": f"The password is {secret}"}],
        response=f"typed {secret}",
        input_tokens=10,
        output_tokens=5,
        latency_ms=42,
    )
    masked = trace_svc.mask_trace_payload(payload)
    raw = json.dumps(masked)
    assert secret not in raw
    assert "***" in raw
    assert masked["system"] == "Login with password ***"
    assert masked["response"] == "typed ***"


def test_persist_llm_trace_creates_artifact(artifact_tmp: Path, seeded_run: str) -> None:
    artifact_context.set_run_context(seeded_run, node_id="n-trace", step_index=3)
    row = trace_svc.record_llm_trace(
        model="gpt-4o-mini",
        system="You are helpful.",
        messages=[{"role": "user", "content": "hello"}],
        response='{"ok": true}',
        input_tokens=100,
        output_tokens=20,
        latency_ms=88,
    )
    assert row is not None
    assert row.kind == "llm_trace"
    assert row.node_id == "n-trace"
    assert row.step_index == 3
    assert row.content_type == "application/json"

    stored = json.loads(artifact_svc.resolve_path(row).read_text(encoding="utf-8"))
    assert stored["model"] == "gpt-4o-mini"
    assert stored["tokens"] == {"input": 100, "output": 20}
    assert stored["latency_ms"] == 88
    assert stored["response"] == '{"ok": true}'


def test_llm_trace_api_list_and_fetch(artifact_tmp: Path, seeded_run: str) -> None:
    artifact_context.set_run_context(seeded_run, node_id="api-node")
    row = trace_svc.record_llm_trace(
        model="gpt-4o",
        messages=[{"role": "user", "content": "ping"}],
        response="pong",
        input_tokens=1,
        output_tokens=1,
        latency_ms=5,
    )
    assert row is not None

    client = TestClient(app)
    list_resp = client.get(f"/api/runs/{seeded_run}/artifacts?kind=llm_trace")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["id"] == row.id
    assert items[0]["kind"] == "llm_trace"
    assert items[0]["node_id"] == "api-node"

    fetch_resp = client.get(f"/api/runs/{seeded_run}/artifacts/{row.id}")
    assert fetch_resp.status_code == 200
    body = json.loads(fetch_resp.content.decode("utf-8"))
    assert body["response"] == "pong"
    assert body["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_text_prompt_writes_masked_trace(
    monkeypatch: pytest.MonkeyPatch,
    artifact_tmp: Path,
    seeded_run: str,
) -> None:
    from app.nodes import text_prompt

    secret = "hunter2-secret-value"
    artifact_context.set_run_context(seeded_run, node_id="tp-mask")
    artifact_context.register_sensitive("password", secret)

    usage = MagicMock()
    usage.prompt_token_count = 12
    usage.candidates_token_count = 3
    response = MagicMock()
    response.text = '{"status":"ok"}'
    response.usage_metadata = usage

    async def fake_generate_content(**_: Any) -> MagicMock:
        return response

    client = MagicMock()
    client.aio.models.generate_content = fake_generate_content
    monkeypatch.setattr(text_prompt, "llm_is_configured", lambda: True)
    monkeypatch.setattr("app.agents.model.get_genai_client", lambda: client)
    monkeypatch.setattr("app.agents.model.get_genai_model_id", lambda: "gpt-4o")

    prompt = f"Use password {secret} to continue"
    await text_prompt.run(
        {"prompt": prompt},
        input_items=[],
        context={},
    )

    traces = artifact_svc.list_artifacts(seeded_run, kind="llm_trace")
    assert len(traces) == 1
    payload = json.loads(artifact_svc.resolve_path(traces[0]).read_text(encoding="utf-8"))
    assert secret not in json.dumps(payload)
    assert payload["messages"][0]["content"] == f"Use password *** to continue"
