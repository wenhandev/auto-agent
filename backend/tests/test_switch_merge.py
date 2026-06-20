"""Tests for ``switch`` routing and ``merge`` modes under the DAG scheduler."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app import executor
from app.nodes.result import Item, NodeResult
from app.schemas import Edge, Node, Workflow


def _run(workflow: Workflow) -> list[dict]:
    events: list[dict] = []

    async def on_event(payload: dict) -> None:
        events.append(payload)

    asyncio.run(executor.run_workflow(workflow, on_event))
    return events


def _completed(events: list[dict]) -> dict[str, dict]:
    return {
        e["node_id"]: e for e in events if e["event"] == "node_completed"
    }


def _emit_items(monkeypatch: Any, mapping: dict[str, list[dict]]) -> None:
    """Stub ``extract`` so a node's instruction keys into ``mapping`` items."""

    async def fake_extract(instruction: str):
        items = [Item(json=dict(j)) for j in mapping.get(instruction, [{}])]
        return NodeResult.from_items(items)

    monkeypatch.setattr(executor.actions, "extract", fake_extract)


def test_switch_matching_case_selected(monkeypatch):
    wf = Workflow(
        nodes=[
            Node(id="s", type="start", label="s"),
            Node(id="sw", type="switch", label="sw", params={"expr": "'paid'"}),
            Node(id="paid", type="start", label="paid"),
            Node(id="pending", type="start", label="pending"),
            Node(id="other", type="start", label="other"),
        ],
        edges=[
            Edge(id="e0", source="s", target="sw"),
            Edge(id="ep", source="sw", target="paid", case="paid"),
            Edge(id="epd", source="sw", target="pending", case="pending"),
            Edge(id="ed", source="sw", target="other", case=None),
        ],
        start_id="s",
    )
    events = _run(wf)
    completed = _completed(events)
    skipped = [e["node_id"] for e in events if e["event"] == "node_skipped"]
    assert "paid" in completed
    assert "pending" in skipped
    assert "other" in skipped
    assert events[-1]["event"] == "run_completed"


def test_switch_default_fallback(monkeypatch):
    wf = Workflow(
        nodes=[
            Node(id="s", type="start", label="s"),
            Node(id="sw", type="switch", label="sw", params={"expr": "'unknown'"}),
            Node(id="paid", type="start", label="paid"),
            Node(id="dflt", type="start", label="default"),
        ],
        edges=[
            Edge(id="e0", source="s", target="sw"),
            Edge(id="ep", source="sw", target="paid", case="paid"),
            Edge(id="ed", source="sw", target="dflt", case=None),
        ],
        start_id="s",
    )
    events = _run(wf)
    completed = _completed(events)
    skipped = [e["node_id"] for e in events if e["event"] == "node_skipped"]
    assert "dflt" in completed
    assert "paid" in skipped
    assert events[-1]["event"] == "run_completed"


def test_switch_no_match_no_default_fails(monkeypatch):
    wf = Workflow(
        nodes=[
            Node(id="s", type="start", label="s"),
            Node(id="sw", type="switch", label="sw", params={"expr": "'x'"}),
            Node(id="paid", type="start", label="paid"),
        ],
        edges=[
            Edge(id="e0", source="s", target="sw"),
            Edge(id="ep", source="sw", target="paid", case="paid"),
        ],
        start_id="s",
    )
    events = _run(wf)
    failed = [e for e in events if e["event"] == "run_failed"]
    assert failed
    assert "no case matched 'x' and no default edge" in failed[0]["error"]


def test_merge_append_concatenates(monkeypatch):
    _emit_items(monkeypatch, {"B": [{"x": 1}], "C": [{"x": 2}, {"x": 3}]})
    wf = Workflow(
        nodes=[
            Node(id="a", type="start", label="a"),
            Node(id="b", type="extract", label="b", params={"instruction": "B"}),
            Node(id="c", type="extract", label="c", params={"instruction": "C"}),
            Node(id="m", type="merge", label="m", params={"mode": "append"}),
        ],
        edges=[
            Edge(id="ab", source="a", target="b"),
            Edge(id="ac", source="a", target="c"),
            Edge(id="bm", source="b", target="m"),
            Edge(id="cm", source="c", target="m"),
        ],
        start_id="a",
    )
    events = _run(wf)
    m = _completed(events)["m"]
    assert m["items_count"] == 3
    # b's item first, then c's two items.
    assert m["items_preview"]["json"] == {"x": 1}


def test_merge_by_key_joins(monkeypatch):
    _emit_items(
        monkeypatch,
        {"B": [{"id": 1, "a": "A"}], "C": [{"id": 1, "b": "B"}]},
    )
    wf = Workflow(
        nodes=[
            Node(id="a", type="start", label="a"),
            Node(id="b", type="extract", label="b", params={"instruction": "B"}),
            Node(id="c", type="extract", label="c", params={"instruction": "C"}),
            Node(
                id="m",
                type="merge",
                label="m",
                params={"mode": "merge_by_key", "key": "id"},
            ),
        ],
        edges=[
            Edge(id="ab", source="a", target="b"),
            Edge(id="ac", source="a", target="c"),
            Edge(id="bm", source="b", target="m"),
            Edge(id="cm", source="c", target="m"),
        ],
        start_id="a",
    )
    events = _run(wf)
    m = _completed(events)["m"]
    assert m["items_count"] == 1
    assert m["output"] == {"id": 1, "a": "A", "b": "B"}


def test_wait_all_keys_by_parent_id(monkeypatch):
    _emit_items(monkeypatch, {"B": [{"ob": 1}], "C": [{"oc": 2}]})
    wf = Workflow(
        nodes=[
            Node(id="a", type="start", label="a"),
            Node(id="b", type="extract", label="b", params={"instruction": "B"}),
            Node(id="c", type="extract", label="c", params={"instruction": "C"}),
            Node(id="m", type="merge", label="m", params={"mode": "wait_all"}),
        ],
        edges=[
            Edge(id="ab", source="a", target="b"),
            Edge(id="ac", source="a", target="c"),
            Edge(id="bm", source="b", target="m"),
            Edge(id="cm", source="c", target="m"),
        ],
        start_id="a",
    )
    events = _run(wf)
    m = _completed(events)["m"]
    assert m["items_count"] == 1
    assert m["output"] == {"b": {"ob": 1}, "c": {"oc": 2}}


def test_merge_after_skipped_branch_no_deadlock(monkeypatch):
    # cond selects true -> b runs; the false branch (c) is skipped/pruned.
    # m is an append merge of b (live) and c (skipped) -> emits b's items only.
    _emit_items(monkeypatch, {"B": [{"x": 1}]})
    wf = Workflow(
        nodes=[
            Node(id="s", type="start", label="s"),
            Node(id="cond", type="condition", label="cond", params={"expr": "True"}),
            Node(id="b", type="extract", label="b", params={"instruction": "B"}),
            Node(id="c", type="start", label="c"),
            Node(id="m", type="merge", label="m", params={"mode": "append"}),
        ],
        edges=[
            Edge(id="e0", source="s", target="cond"),
            Edge(id="et", source="cond", target="b", when="true"),
            Edge(id="ef", source="cond", target="c", when="false"),
            Edge(id="bm", source="b", target="m"),
            Edge(id="cm", source="c", target="m"),
        ],
        start_id="s",
    )
    events = _run(wf)
    completed = _completed(events)
    skipped = [e["node_id"] for e in events if e["event"] == "node_skipped"]
    assert "c" in skipped
    assert "m" in completed
    assert completed["m"]["items_count"] == 1
    assert completed["m"]["output"] == {"x": 1}
    assert events[-1]["event"] == "run_completed"
