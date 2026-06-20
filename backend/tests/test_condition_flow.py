"""Tests for safe condition/switch evaluation (if-condition-flow)."""

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
from app.services.flow_conditions import (
    FlowConditionError,
    build_flow_namespace,
    evaluate_condition,
    evaluate_switch_case,
)
from app.services.expressions import ExpressionError


def test_predicate_numeric_comparison():
    params = {
        "predicate": {"left": 500, "op": ">=", "right": 400},
    }
    out = evaluate_condition(params, namespace=build_flow_namespace())
    assert out["result"] is True
    assert out["condition"] is True


def test_whole_field_bool_expr():
    params = {"expr": True}
    out = evaluate_condition(params, namespace=build_flow_namespace())
    assert out["result"] is True


def test_legacy_empty_defaults_true():
    out = evaluate_condition({}, namespace=build_flow_namespace())
    assert out["result"] is True


def test_legacy_expr_true_false_strings():
    assert evaluate_condition({"expr": "True"}, namespace=build_flow_namespace())["result"]
    assert not evaluate_condition({"expr": "False"}, namespace=build_flow_namespace())["result"]


def test_predicate_precedence_over_expr():
    params = {
        "predicate": {"left": 1, "op": "==", "right": 2},
        "expr": "True",
    }
    out = evaluate_condition(params, namespace=build_flow_namespace())
    assert out["result"] is False


def test_malicious_expr_rejected():
    with pytest.raises(FlowConditionError):
        evaluate_condition(
            {"expr": "{{= __import__('os').system('id') }}"},
            namespace=build_flow_namespace(),
        )


def test_switch_matching_and_default():
    ns = build_flow_namespace()
    assert evaluate_switch_case({"expr": "'paid'"}, namespace=ns) == "paid"
    assert evaluate_switch_case({"expr": "'unknown'"}, namespace=ns) == "unknown"


def test_switch_whole_expression():
    ns = build_flow_namespace(
        context={
            "n1": NodeResult.from_items([Item(json={"status": "paid"})]),
        }
    )
    key = evaluate_switch_case(
        {"expr": "{{= nodes.n1.output.status }}"},
        namespace=ns,
    )
    assert key == "paid"


def _run(workflow: Workflow) -> list[dict]:
    events: list[dict] = []

    async def on_event(payload: dict) -> None:
        events.append(payload)

    asyncio.run(executor.run_workflow(workflow, on_event))
    return events


def test_condition_scheduler_prunes_false_branch():
    wf = Workflow(
        nodes=[
            Node(id="s", type="start", label="s"),
            Node(id="cond", type="condition", label="cond", params={"expr": "False"}),
            Node(id="t", type="start", label="true path"),
            Node(id="f", type="start", label="false path"),
        ],
        edges=[
            Edge(id="e0", source="s", target="cond"),
            Edge(id="et", source="cond", target="t", when="true"),
            Edge(id="ef", source="cond", target="f", when="false"),
        ],
        start_id="s",
    )
    events = _run(wf)
    skipped = [e["node_id"] for e in events if e["event"] == "node_skipped"]
    completed = [e["node_id"] for e in events if e["event"] == "node_completed"]
    assert "t" in skipped
    assert "f" in completed
    assert "cond" in completed


def test_switch_no_match_fails():
    wf = Workflow(
        nodes=[
            Node(id="s", type="start", label="s"),
            Node(id="sw", type="switch", label="sw", params={"expr": "'x'"}),
            Node(id="a", type="start", label="a"),
        ],
        edges=[
            Edge(id="e0", source="s", target="sw"),
            Edge(id="ea", source="sw", target="a", case="paid"),
        ],
        start_id="s",
    )
    events = _run(wf)
    assert any(e["event"] == "node_failed" and e["node_id"] == "sw" for e in events)
