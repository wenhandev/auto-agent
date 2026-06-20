"""Unit tests for on_error policy, edge kind routing, and completed_with_errors."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app import executor
from app.schemas import Edge, Node, Workflow


def _run(workflow: Workflow) -> list[dict]:
    events: list[dict] = []

    async def on_event(payload: dict) -> None:
        events.append(payload)

    asyncio.run(executor.run_workflow(workflow, on_event))
    return events


def _stub_navigate_ok(monkeypatch: Any):
    async def fake_navigate(url: str):
        return {"url": url}

    monkeypatch.setattr(executor.actions, "navigate", fake_navigate)


def test_fail_run_default_unchanged(monkeypatch: Any):
    async def fail_navigate(url: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(executor.actions, "navigate", fail_navigate)

    wf = Workflow(
        nodes=[
            Node(id="n1", type="navigate", label="fail", params={"url": "https://x"}),
        ],
        edges=[],
        start_id="n1",
    )
    events = _run(wf)
    assert events[-1]["event"] == "run_failed"
    assert [e for e in events if e["event"] == "node_failed"]


def test_continue_follows_next_edge(monkeypatch: Any):
    calls: list[str] = []

    async def fail_then_ok(url: str):
        if "fail" in url:
            raise RuntimeError("click failed")
        calls.append(url)
        return {"url": url}

    monkeypatch.setattr(executor.actions, "navigate", fail_then_ok)

    wf = Workflow(
        nodes=[
            Node(
                id="n1",
                type="navigate",
                label="fail",
                params={"url": "https://fail"},
                on_error="continue",
            ),
            Node(id="n2", type="navigate", label="next", params={"url": "https://ok"}),
            Node(id="n3", type="end", label="end"),
        ],
        edges=[
            Edge(id="e1", source="n1", target="n2", kind="next"),
            Edge(id="e2", source="n2", target="n3", kind="next"),
        ],
        start_id="n1",
    )
    events = _run(wf)
    started = [e["node_id"] for e in events if e["event"] == "node_started"]
    assert "n2" in started
    assert calls == ["https://ok"]
    assert events[-1]["event"] == "run_completed_with_errors"
    assert events[-1]["failed_node_count"] == 1
    assert events[-1]["failed_node_ids"] == ["n1"]


def test_branch_follows_on_error_edge(monkeypatch: Any):
    calls: list[str] = []

    async def route_navigate(url: str):
        calls.append(url)
        if "fail" in url:
            raise RuntimeError("failed")
        return {"url": url}

    monkeypatch.setattr(executor.actions, "navigate", route_navigate)

    wf = Workflow(
        nodes=[
            Node(
                id="n1",
                type="navigate",
                label="fail",
                params={"url": "https://fail"},
                on_error="branch",
            ),
            Node(id="n2", type="navigate", label="happy", params={"url": "https://happy"}),
            Node(id="n3", type="navigate", label="cleanup", params={"url": "https://cleanup"}),
            Node(id="n4", type="end", label="end"),
        ],
        edges=[
            Edge(id="e1", source="n1", target="n2", kind="next"),
            Edge(id="e2", source="n1", target="n3", kind="on_error"),
            Edge(id="e3", source="n3", target="n4", kind="next"),
        ],
        start_id="n1",
    )
    events = _run(wf)
    started = [e["node_id"] for e in events if e["event"] == "node_started"]
    assert "n3" in started
    assert "n2" not in started
    assert "https://cleanup" in calls
    assert "https://happy" not in calls
    assert events[-1]["event"] == "run_completed_with_errors"


def test_branch_without_on_error_edge_degrades(monkeypatch: Any):
    async def fail_navigate(url: str):
        raise RuntimeError("failed hard")

    monkeypatch.setattr(executor.actions, "navigate", fail_navigate)

    wf = Workflow(
        nodes=[
            Node(
                id="n1",
                type="navigate",
                label="fail",
                params={"url": "https://fail"},
                on_error="branch",
            ),
            Node(id="n2", type="navigate", label="next", params={"url": "https://ok"}),
        ],
        edges=[Edge(id="e1", source="n1", target="n2", kind="next")],
        start_id="n1",
    )
    events = _run(wf)
    failed = [e for e in events if e["event"] == "node_failed"]
    assert len(failed) == 1
    assert "falling back to fail_run" in failed[0]["error"]
    assert events[-1]["event"] == "run_failed"


def test_all_green_run_completes_normally(monkeypatch: Any):
    _stub_navigate_ok(monkeypatch)

    wf = Workflow(
        nodes=[
            Node(id="n1", type="navigate", label="a", params={"url": "https://a"}),
            Node(id="n2", type="navigate", label="b", params={"url": "https://b"}),
        ],
        edges=[Edge(id="e1", source="n1", target="n2")],
        start_id="n1",
    )
    events = _run(wf)
    assert events[-1]["event"] == "run_completed"
    assert [e for e in events if e["event"] == "node_failed"] == []


def test_branch_reaches_end_without_tolerated_flag_is_completed(monkeypatch: Any):
    """Branch to cleanup that succeeds then end — still completed_with_errors."""
    _stub_navigate_ok(monkeypatch)

    async def fail_once(url: str):
        if "fail" in url:
            raise RuntimeError("nope")
        return {"url": url}

    monkeypatch.setattr(executor.actions, "navigate", fail_once)

    wf = Workflow(
        nodes=[
            Node(
                id="n1",
                type="navigate",
                label="fail",
                params={"url": "https://fail"},
                on_error="branch",
            ),
            Node(id="n2", type="navigate", label="cleanup", params={"url": "https://ok"}),
            Node(id="n3", type="end", label="end"),
        ],
        edges=[
            Edge(id="e1", source="n1", target="n2", kind="on_error"),
            Edge(id="e2", source="n2", target="n3", kind="next"),
        ],
        start_id="n1",
    )
    events = _run(wf)
    assert events[-1]["event"] == "run_completed_with_errors"
