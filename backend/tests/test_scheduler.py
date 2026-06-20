"""Tests for the indegree ready-queue DAG scheduler.

Actions are stubbed (monkeypatched) so no browser is required, mirroring the
pattern in ``tests/test_items_envelope.py``.
"""
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


def _stub_navigate(monkeypatch: Any) -> None:
    async def fake_navigate(url: str):
        return {"url": url}

    monkeypatch.setattr(executor.actions, "navigate", fake_navigate)


def _completed_order(events: list[dict]) -> list[str]:
    return [e["node_id"] for e in events if e["event"] == "node_completed"]


def _started_order(events: list[dict]) -> list[str]:
    return [e["node_id"] for e in events if e["event"] == "node_started"]


def test_linear_chain_parity(monkeypatch):
    _stub_navigate(monkeypatch)
    wf = Workflow(
        nodes=[
            Node(id="n1", type="navigate", label="1", params={"url": "https://1"}),
            Node(id="n2", type="navigate", label="2", params={"url": "https://2"}),
            Node(id="n3", type="navigate", label="3", params={"url": "https://3"}),
        ],
        edges=[
            Edge(id="e1", source="n1", target="n2"),
            Edge(id="e2", source="n2", target="n3"),
        ],
        start_id="n1",
    )
    events = _run(wf)
    assert events[0]["event"] == "run_started"
    assert events[-1]["event"] == "run_completed"
    assert _completed_order(events) == ["n1", "n2", "n3"]
    assert _started_order(events) == ["n1", "n2", "n3"]


def test_diamond_merge_append(monkeypatch):
    # a fans out to b and c; both feed an append merge d.
    async def fake_extract(instruction: str):
        from app.nodes.result import Item, NodeResult

        # encode the instruction so b/c produce distinct items
        return NodeResult.from_items([Item(json={"src": instruction})])

    monkeypatch.setattr(executor.actions, "extract", fake_extract)

    wf = Workflow(
        nodes=[
            Node(id="a", type="start", label="a"),
            Node(id="b", type="extract", label="b", params={"instruction": "B"}),
            Node(id="c", type="extract", label="c", params={"instruction": "C"}),
            Node(id="d", type="merge", label="d", params={"mode": "append"}),
        ],
        edges=[
            Edge(id="ab", source="a", target="b"),
            Edge(id="ac", source="a", target="c"),
            Edge(id="bd", source="b", target="d"),
            Edge(id="cd", source="c", target="d"),
        ],
        start_id="a",
    )
    events = _run(wf)
    order = _completed_order(events)
    # a first, then b & c deterministically (by rank/id), then d exactly once.
    assert order.index("a") < order.index("b")
    assert order.index("a") < order.index("c")
    assert order.index("b") < order.index("c")
    assert order.index("b") < order.index("d")
    assert order.index("c") < order.index("d")
    assert order.count("d") == 1
    d = [e for e in events if e["event"] == "node_completed" and e["node_id"] == "d"][0]
    assert d["items_count"] == 2
    # b's item then c's item, concatenated in edge order.
    completed = {
        e["node_id"]: e
        for e in events
        if e["event"] == "node_completed"
    }
    assert completed["d"]["output"] == {"src": "B"}
    assert events[-1]["event"] == "run_completed"


def test_pruning_and_skip_propagation(monkeypatch):
    # condition false -> prune the true branch (b -> b2), skipping both.
    wf = Workflow(
        nodes=[
            Node(id="s", type="start", label="s"),
            Node(id="cond", type="condition", label="cond", params={"expr": "False"}),
            Node(id="b", type="start", label="b"),
            Node(id="b2", type="start", label="b2"),
            Node(id="c", type="start", label="c"),
        ],
        edges=[
            Edge(id="e0", source="s", target="cond"),
            Edge(id="et", source="cond", target="b", when="true"),
            Edge(id="ef", source="cond", target="c", when="false"),
            Edge(id="eb", source="b", target="b2"),
        ],
        start_id="s",
    )
    events = _run(wf)
    completed = _completed_order(events)
    skipped = [e["node_id"] for e in events if e["event"] == "node_skipped"]
    pruned = [e for e in events if e["event"] == "branch_pruned"]
    assert "c" in completed
    assert "b" in skipped
    assert "b2" in skipped  # skip propagates downstream
    assert "b" not in completed
    # the true edge to b was pruned
    assert any(e["edge_id"] == "et" for e in pruned)
    assert events[-1]["event"] == "run_completed"


def test_node_with_one_live_one_pruned_parent_runs(monkeypatch):
    # cond selects false -> c. d has parents b (skipped/pruned) and c (live).
    wf = Workflow(
        nodes=[
            Node(id="s", type="start", label="s"),
            Node(id="cond", type="condition", label="cond", params={"expr": "False"}),
            Node(id="b", type="start", label="b"),
            Node(id="c", type="start", label="c"),
            Node(id="d", type="start", label="d"),
        ],
        edges=[
            Edge(id="e0", source="s", target="cond"),
            Edge(id="et", source="cond", target="b", when="true"),
            Edge(id="ef", source="cond", target="c", when="false"),
            Edge(id="bd", source="b", target="d"),
            Edge(id="cd", source="c", target="d"),
        ],
        start_id="s",
    )
    events = _run(wf)
    completed = _completed_order(events)
    skipped = [e["node_id"] for e in events if e["event"] == "node_skipped"]
    assert "c" in completed
    assert "b" in skipped
    assert "d" in completed  # one live parent is enough
    assert events[-1]["event"] == "run_completed"


def test_illegal_cycle_fails(monkeypatch):
    wf = Workflow(
        nodes=[
            Node(id="n1", type="start", label="1"),
            Node(id="n2", type="start", label="2"),
        ],
        edges=[
            Edge(id="e1", source="n1", target="n2"),
            Edge(id="e2", source="n2", target="n1"),
        ],
        start_id="n1",
    )
    events = _run(wf)
    failed = [e for e in events if e["event"] == "run_failed"]
    assert failed
    assert "cycle detected" in failed[0]["error"]


def test_branch_pruned_and_node_skipped_events(monkeypatch):
    wf = Workflow(
        nodes=[
            Node(id="s", type="start", label="s"),
            Node(id="cond", type="condition", label="cond", params={"expr": "True"}),
            Node(id="t", type="start", label="t"),
            Node(id="f", type="start", label="f"),
        ],
        edges=[
            Edge(id="e0", source="s", target="cond"),
            Edge(id="et", source="cond", target="t", when="true"),
            Edge(id="ef", source="cond", target="f", when="false"),
        ],
        start_id="s",
    )
    events = _run(wf)
    pruned = [e for e in events if e["event"] == "branch_pruned"]
    skipped = [e["node_id"] for e in events if e["event"] == "node_skipped"]
    assert any(e["edge_id"] == "ef" and e["node_id"] == "cond" for e in pruned)
    assert "f" in skipped
    assert "t" in _completed_order(events)
