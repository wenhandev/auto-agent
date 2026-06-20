from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app import executor
from app.nodes.result import Item, NodeResult
from app.schemas import Edge, Node, Workflow


def test_single_wrap():
    r = NodeResult.single({"url": "https://x", "title": "X"})
    assert r.output == {"url": "https://x", "title": "X"}
    assert len(r.items) == 1
    assert r.items[0].json == r.output


def test_none_becomes_empty_dict():
    r = NodeResult.single(None)
    assert r.output == {}
    assert r.items[0].json == {}


def test_multi_item_output_is_first():
    r = NodeResult.from_items([Item(json={"sku": "A"}), Item(json={"sku": "B"})])
    assert r.output == {"sku": "A"}


def test_coerce_result_passthrough():
    nr = NodeResult.single({"a": 1})
    assert executor._coerce_result(nr) is nr
    items = [Item(json={"x": 1}), Item(json={"x": 2})]
    coerced = executor._coerce_result(items)
    assert coerced.output == {"x": 1}
    assert len(coerced.items) == 2
    assert executor._coerce_result({"k": "v"}).output == {"k": "v"}


def _collect_run(workflow: Workflow, monkeypatch: Any) -> list[dict]:
    events: list[dict] = []

    async def on_event(payload: dict) -> None:
        events.append(payload)

    asyncio.run(executor.run_workflow(workflow, on_event))
    return events


def test_run_threads_context_and_emits_items_count(monkeypatch):
    # stub navigate/extract so no browser is needed
    async def fake_navigate(url: str):
        return {"url": url, "title": "Home"}

    monkeypatch.setattr(executor.actions, "navigate", fake_navigate)

    wf = Workflow(
        nodes=[
            Node(id="s", type="start", label="start"),
            Node(id="nav", type="navigate", label="go", params={"url": "https://a"}),
            Node(
                id="nav2",
                type="navigate",
                label="go2",
                params={"url": "https://b/{{nodes.nav.output.title}}"},
            ),
            Node(id="e", type="end", label="end"),
        ],
        edges=[
            Edge(id="e1", source="s", target="nav"),
            Edge(id="e2", source="nav", target="nav2"),
            Edge(id="e3", source="nav2", target="e"),
        ],
        start_id="s",
    )
    events = _collect_run(wf, monkeypatch)
    completed = [e for e in events if e["event"] == "node_completed"]
    by_id = {e["node_id"]: e for e in completed}
    assert by_id["nav"]["items_count"] == 1
    assert by_id["nav"]["output"] == {"url": "https://a", "title": "Home"}
    # interpolation used nav's output title into nav2's url
    assert by_id["nav2"]["output"] == {"url": "https://b/Home", "title": "Home"}
    assert events[-1]["event"] == "run_completed"


def test_node_completed_has_items_preview(monkeypatch):
    async def fake_navigate(url: str):
        return {"url": url}

    monkeypatch.setattr(executor.actions, "navigate", fake_navigate)
    wf = Workflow(
        nodes=[
            Node(id="s", type="start", label="s"),
            Node(id="n", type="navigate", label="n", params={"url": "https://a"}),
            Node(id="e", type="end", label="e"),
        ],
        edges=[
            Edge(id="e1", source="s", target="n"),
            Edge(id="e2", source="n", target="e"),
        ],
        start_id="s",
    )
    events = _collect_run(wf, monkeypatch)
    n = [e for e in events if e.get("node_id") == "n" and e["event"] == "node_completed"][0]
    assert "items_preview" in n
    assert n["items_preview"]["json"] == {"url": "https://a"}
