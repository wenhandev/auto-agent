"""Tests for vision-and-utility-blocks backend nodes."""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app import executor
from app.nodes import (
    file_download,
    file_upload,
    goto_url,
    print_page,
    text_prompt,
    validation,
    while_loop,
)
from app.nodes.result import Item, NodeResult
from app.schemas import Edge, Node, Workflow
from app.services import artifact_context
from app.services import artifacts as artifact_svc
from app.services.predicate import evaluate_predicate
from app.tools.sandbox import SandboxViolation, workflow_dir


def test_evaluate_predicate_operators() -> None:
    assert evaluate_predicate(3, ">", 1)
    assert evaluate_predicate("a", "in", ["a", "b"])
    assert evaluate_predicate("", "is_falsy")
    assert not evaluate_predicate("x", "==", "y")


@pytest.mark.asyncio
async def test_validation_passes() -> None:
    items = await validation.run(
        {"predicate": {"left": 2, "op": "==", "right": 2}},
        input_items=[Item(json={})],
        context={},
    )
    assert items[0].json["passed"] is True
    assert "reason" not in items[0].json


@pytest.mark.asyncio
async def test_validation_fails_with_reason() -> None:
    items = await validation.run(
        {"predicate": {"left": 1, "op": ">=", "right": 5}},
        input_items=[Item(json={})],
        context={},
    )
    assert items[0].json["passed"] is False
    assert "reason" in items[0].json


def test_validation_fail_run_emits_event(monkeypatch: Any) -> None:
    events: list[dict] = []

    async def on_event(payload: dict) -> None:
        events.append(payload)

    wf = Workflow(
        nodes=[
            Node(
                id="v1",
                type="validation",
                label="check",
                params={"predicate": {"left": 0, "op": "is_truthy"}},
                on_error="fail_run",
            ),
        ],
        edges=[],
        start_id="v1",
    )
    asyncio.run(executor.run_workflow(wf, on_event))
    assert any(e["event"] == "validation_failed" for e in events)
    assert events[-1]["event"] == "run_failed"


def test_validation_continue_follows_next(monkeypatch: Any) -> None:
    calls: list[str] = []

    async def fake_goto(params: dict[str, Any]) -> dict[str, Any]:
        calls.append(params["url"])
        return {"url": params["url"]}

    monkeypatch.setattr(goto_url, "run", fake_goto)

    events: list[dict] = []

    async def on_event(payload: dict) -> None:
        events.append(payload)

    wf = Workflow(
        nodes=[
            Node(
                id="v1",
                type="validation",
                label="check",
                params={"predicate": {"left": 0, "op": "is_truthy"}},
                on_error="continue",
            ),
            Node(id="g1", type="goto_url", label="next", params={"url": "https://ok"}),
            Node(id="end", type="end", label="end"),
        ],
        edges=[
            Edge(id="e1", source="v1", target="g1", kind="next"),
            Edge(id="e2", source="g1", target="end", kind="next"),
        ],
        start_id="v1",
    )
    asyncio.run(executor.run_workflow(wf, on_event))
    assert calls == ["https://ok"]
    assert events[-1]["event"] == "run_completed"


def test_validation_branch_follows_on_error(monkeypatch: Any) -> None:
    calls: list[str] = []

    async def fake_goto(params: dict[str, Any]) -> dict[str, Any]:
        calls.append(params["url"])
        return {"url": params["url"]}

    monkeypatch.setattr(goto_url, "run", fake_goto)

    wf = Workflow(
        nodes=[
            Node(
                id="v1",
                type="validation",
                label="check",
                params={"predicate": {"left": "", "op": "is_truthy"}},
                on_error="branch",
            ),
            Node(id="happy", type="goto_url", label="happy", params={"url": "https://happy"}),
            Node(id="err", type="goto_url", label="err", params={"url": "https://err"}),
            Node(id="end", type="end", label="end"),
        ],
        edges=[
            Edge(id="e1", source="v1", target="happy", kind="next"),
            Edge(id="e2", source="v1", target="err", kind="on_error"),
            Edge(id="e3", source="err", target="end", kind="next"),
        ],
        start_id="v1",
    )
    events: list[dict] = []

    async def on_event(payload: dict) -> None:
        events.append(payload)

    asyncio.run(executor.run_workflow(wf, on_event))
    assert calls == ["https://err"]
    assert events[-1]["event"] == "run_completed"


@pytest.mark.asyncio
async def test_text_prompt_without_schema_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(text_prompt, "llm_is_configured", lambda: False)
    items = await text_prompt.run(
        {"prompt": "Summarize this"},
        input_items=[],
        context={},
    )
    assert "text" in items[0].json


@pytest.mark.asyncio
async def test_text_prompt_schema_repair(monkeypatch: pytest.MonkeyPatch) -> None:
    schema = {
        "type": "object",
        "properties": {"title": {"type": "string"}},
        "required": ["title"],
    }

    async def fake_call(*, prompt: str, system: str | None) -> str:
        if "repair" in prompt.lower() or "schema" in prompt.lower():
            return '{"title": "Fixed"}'
        return "not-json"

    monkeypatch.setattr(text_prompt, "llm_is_configured", lambda: True)
    monkeypatch.setattr(text_prompt, "_call_llm", fake_call)

    items = await text_prompt.run(
        {"prompt": "get title", "schema": schema},
        input_items=[],
        context={},
    )
    assert items[0].json["title"] == "Fixed"


@pytest.mark.asyncio
async def test_goto_url_navigates(monkeypatch: pytest.MonkeyPatch) -> None:
    page = AsyncMock()
    page.url = "https://example.com/"
    page.title = AsyncMock(return_value="Example")

    async def fake_get_page():
        return page

    monkeypatch.setattr("app.nodes.goto_url.get_page", fake_get_page)

    out = await goto_url.run({"url": "https://example.com"})
    page.goto.assert_awaited_once_with("https://example.com", wait_until="load")
    assert out["url"] == "https://example.com/"


@pytest.fixture
def artifact_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "artifacts"
    artifact_svc.set_artifact_root(root)
    artifact_svc.reset_seq_counters()
    monkeypatch.setattr("app.settings.settings.max_artifact_bytes", 1024 * 1024)
    yield root
    artifact_svc.reset_artifact_root()
    artifact_svc.reset_seq_counters()
    artifact_context.clear_run_context()


@pytest.mark.asyncio
async def test_print_page_stores_pdf(
    artifact_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_context.set_run_context("run-print-1", node_id="p1")
    page = AsyncMock()
    page.pdf = AsyncMock(return_value=b"%PDF-1.4 test")

    async def fake_get_page():
        return page

    monkeypatch.setattr("app.nodes.print_page.get_page", fake_get_page)

    out = await print_page.run({}, node_id="p1")
    assert out["filename"] == "page.pdf"
    assert out["bytes"] == len(b"%PDF-1.4 test")
    assert artifact_svc.get_artifact(out["artifact_id"], run_id="run-print-1") is not None


@pytest.fixture
def wf_id():
    wid = f"test_{uuid.uuid4().hex[:8]}"
    yield wid
    import shutil

    shutil.rmtree(workflow_dir(wid), ignore_errors=True)


@pytest.mark.asyncio
async def test_file_upload_from_sandbox(wf_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    path = workflow_dir(wf_id) / "upload.txt"
    path.write_text("payload")

    page = MagicMock()
    locator = MagicMock()
    locator.set_input_files = AsyncMock()
    page.locator.return_value = locator

    async def fake_get_page():
        return page

    monkeypatch.setattr("app.nodes.file_upload.get_page", fake_get_page)

    out = await file_upload.run(
        {"file": "upload.txt", "target": "#file-input"},
        workflow_id=wf_id,
    )
    locator.set_input_files.assert_awaited_once_with(str(path))
    assert out["uploaded"] is True


@pytest.mark.asyncio
async def test_file_upload_traversal_rejected(wf_id: str) -> None:
    with pytest.raises(SandboxViolation):
        await file_upload.run(
            {"file": "../../escape.txt", "target": "#f"},
            workflow_id=wf_id,
        )


@pytest.mark.asyncio
async def test_file_download_captures_artifact(
    artifact_tmp: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact_context.set_run_context("run-dl-1", node_id="d1")
    dl_path = tmp_path / "report.csv"
    dl_path.write_bytes(b"a,b,c")

    download = AsyncMock()
    download.path = AsyncMock(return_value=str(dl_path))
    download.suggested_filename = "report.csv"

    from contextlib import asynccontextmanager

    async def get_download():
        return download

    download_info = MagicMock()
    download_info.value = get_download()

    @asynccontextmanager
    async def fake_expect_download(timeout: int = 0):
        yield download_info

    page = MagicMock()
    page.expect_download = fake_expect_download
    locator = MagicMock()
    locator.click = AsyncMock()
    page.locator.return_value = locator

    async def fake_get_page():
        return page

    monkeypatch.setattr("app.nodes.file_download.get_page", fake_get_page)

    out = await file_download.run({"target": "#dl"}, node_id="d1")
    assert out["filename"] == "report.csv"
    assert out["bytes"] == 5
    row = artifact_svc.get_artifact(out["artifact_id"], run_id="run-dl-1")
    assert row is not None
    assert row.kind == "download"


@pytest.mark.asyncio
async def test_while_loop_cap_and_events(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict] = []

    async def emit(event: str, *, node_id: str | None = None, **extra: Any) -> None:
        events.append({"event": event, "node_id": node_id, **extra})

    body = Workflow(
        nodes=[Node(id="noop", type="end", label="end")],
        edges=[],
        start_id="noop",
    )

    async def fake_execute_dag(workflow, emit_fn, **kwargs):
        await emit_fn({"event": "run_completed"})

    monkeypatch.setattr("app.exec.scheduler.execute_dag", fake_execute_dag)

    items = await while_loop.run(
        {
            "predicate": {"left": 1, "op": "==", "right": 1},
            "body_workflow": body.model_dump(),
            "max_iterations": 3,
        },
        input_items=[Item(json={})],
        context={},
        node_id="w1",
        emit=emit,
        run_node=AsyncMock(),
    )
    out = items[0].json
    assert out["iterations"] == 3
    assert out["max_iterations_reached"] is True
    assert out["reason"] == "max_iterations_reached"
    started = [e for e in events if e["event"] == "while_iteration_started"]
    completed = [e for e in events if e["event"] == "while_iteration_completed"]
    assert len(started) == 3
    assert len(completed) == 3


@pytest.mark.asyncio
async def test_while_loop_stops_when_predicate_false(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    async def fake_execute_dag(workflow, emit_fn, **kwargs):
        calls["n"] += 1
        await emit_fn({"event": "run_completed"})

    monkeypatch.setattr("app.exec.scheduler.execute_dag", fake_execute_dag)

    body = Workflow(
        nodes=[Node(id="noop", type="end", label="end")],
        edges=[],
        start_id="noop",
    )

    items = await while_loop.run(
        {
            "predicate": {"left": 0, "op": "is_truthy"},
            "body_workflow": body.model_dump(),
            "max_iterations": 10,
        },
        input_items=[Item(json={})],
        context={},
        node_id="w1",
        emit=None,
        run_node=AsyncMock(),
    )
    assert items[0].json["iterations"] == 0
    assert calls["n"] == 0
