"""Trajectory → draft workflow synthesis tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlmodel import Session, select

from app.agents.autonomous import TrajectoryStep
from app.db.models import Workflow
from app.db.session import engine
from app.services.trajectory_synthesis import (
    _SYNTH_MARKER,
    synthesize_workflow,
    trajectory_to_graph,
)


def test_unstable_step_yields_vision_node() -> None:
    steps = [
        TrajectoryStep(
            step_index=0,
            tool="navigate",
            args={"url": "https://shop.example.com"},
            result={"url": "https://shop.example.com"},
            url="https://shop.example.com",
            stable=False,
        ),
        TrajectoryStep(
            step_index=1,
            tool="click_element",
            args={"index": 2},
            result={"clicked_index": 2},
            url="https://shop.example.com",
            stable=False,
            thought="click add to cart",
        ),
    ]
    graph = trajectory_to_graph("buy item", steps)
    types = {n["type"] for n in graph["nodes"]}
    assert "vision_navigate" in types
    assert "vision_act" in types


def test_stable_navigate_uses_navigate_node() -> None:
    steps = [
        TrajectoryStep(
            step_index=0,
            tool="navigate",
            args={"url": "https://example.com"},
            result={"url": "https://example.com"},
            url="https://example.com",
            stable=True,
        ),
    ]
    graph = trajectory_to_graph("visit", steps)
    nav_nodes = [n for n in graph["nodes"] if n["type"] == "navigate"]
    assert len(nav_nodes) == 1
    assert nav_nodes[0]["params"]["url"] == "https://example.com"


def test_draft_created_with_referenced_id() -> None:
    steps = [
        TrajectoryStep(
            step_index=0,
            tool="wait",
            args={"ms": 10},
            result={"waited_ms": 10},
            url="https://example.com",
            stable=True,
        ),
    ]
    wf_id = synthesize_workflow("demo task", steps)
    assert wf_id

    with Session(engine) as session:
        wf = session.get(Workflow, wf_id)
        assert wf is not None
        assert wf.status == "draft"
        assert _SYNTH_MARKER in (wf.description or "")


def test_draft_graph_has_start_and_end() -> None:
    graph = trajectory_to_graph("x", [])
    ids = {n["id"] for n in graph["nodes"]}
    assert "start" in ids
    assert "end" in ids
    assert graph["start_id"] == "start"
