"""Unit tests for per-node retry policy and node_retry events."""
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
from app.schemas import Edge, Node, RetryPolicy, Workflow


def _run(workflow: Workflow, *, abort_event: asyncio.Event | None = None) -> list[dict]:
    events: list[dict] = []

    async def on_event(payload: dict) -> None:
        events.append(payload)

    asyncio.run(executor.run_workflow(workflow, on_event, abort_event=abort_event))
    return events


def test_no_retry_single_failure(monkeypatch: Any):
    calls = {"n": 0}

    async def fail_navigate(url: str):
        calls["n"] += 1
        raise TimeoutError("boom")

    monkeypatch.setattr(executor.actions, "navigate", fail_navigate)

    wf = Workflow(
        nodes=[
            Node(id="n1", type="navigate", label="go", params={"url": "https://x"}),
        ],
        edges=[],
        start_id="n1",
    )
    events = _run(wf)
    assert calls["n"] == 1
    assert [e["event"] for e in events if e["event"] == "node_retry"] == []
    failed = [e for e in events if e["event"] == "node_failed"]
    assert len(failed) == 1
    assert "attempt" not in failed[0]
    assert events[-1]["event"] == "run_failed"


def test_retry_succeeds_on_second_attempt(monkeypatch: Any):
    calls = {"n": 0}

    async def flaky_navigate(url: str):
        calls["n"] += 1
        if calls["n"] < 2:
            raise TimeoutError("transient")
        return {"url": url}

    monkeypatch.setattr(executor.actions, "navigate", flaky_navigate)

    wf = Workflow(
        nodes=[
            Node(
                id="n1",
                type="navigate",
                label="go",
                params={"url": "https://x"},
                retry=RetryPolicy(max_attempts=3, backoff_ms=10),
            ),
        ],
        edges=[],
        start_id="n1",
    )
    events = _run(wf)
    retries = [e for e in events if e["event"] == "node_retry"]
    assert len(retries) == 1
    assert retries[0]["attempt"] == 1
    completed = [e for e in events if e["event"] == "node_completed"]
    assert len(completed) == 1
    assert completed[0]["attempt"] == 2
    assert events[-1]["event"] == "run_completed"


def test_retry_exhausts_all_attempts(monkeypatch: Any):
    calls = {"n": 0}

    async def always_fail(url: str):
        calls["n"] += 1
        raise TimeoutError(f"fail-{calls['n']}")

    monkeypatch.setattr(executor.actions, "navigate", always_fail)

    wf = Workflow(
        nodes=[
            Node(
                id="n1",
                type="navigate",
                label="go",
                params={"url": "https://x"},
                retry=RetryPolicy(max_attempts=3, backoff_ms=5),
            ),
        ],
        edges=[],
        start_id="n1",
    )
    events = _run(wf)
    retries = [e for e in events if e["event"] == "node_retry"]
    assert len(retries) == 2
    assert [r["attempt"] for r in retries] == [1, 2]
    failed = [e for e in events if e["event"] == "node_failed"]
    assert len(failed) == 1
    assert failed[0]["attempt"] == 3
    assert events[-1]["event"] == "run_failed"


def test_abort_during_retry_sleep(monkeypatch: Any):
    calls = {"n": 0}

    async def flaky_navigate(url: str):
        calls["n"] += 1
        raise TimeoutError("transient")

    monkeypatch.setattr(executor.actions, "navigate", flaky_navigate)

    abort = asyncio.Event()

    async def run_with_abort():
        events: list[dict] = []

        async def on_event(payload: dict) -> None:
            events.append(payload)
            if payload.get("event") == "node_retry":
                abort.set()

        await executor.run_workflow(
            Workflow(
                nodes=[
                    Node(
                        id="n1",
                        type="navigate",
                        label="go",
                        params={"url": "https://x"},
                        retry=RetryPolicy(max_attempts=5, backoff_ms=5000),
                    ),
                ],
                edges=[],
                start_id="n1",
            ),
            on_event,
            abort_event=abort,
        )
        return events

    events = asyncio.run(run_with_abort())
    assert events[-1]["event"] == "run_aborted"
    assert [e for e in events if e["event"] == "node_failed"] == []
    assert calls["n"] == 1


def test_first_attempt_resolution_lock(monkeypatch: Any):
    """Params resolved on attempt 1 must not change on attempt 2."""
    from app.nodes.result import Item, NodeResult

    seen: list[str] = []
    calls = {"n": 0}

    async def fake_dispatch(node, emit, **kwargs):
        calls["n"] += 1
        url = str((node.params or {}).get("url", ""))
        seen.append(url)
        if calls["n"] == 1:
            # Simulate another path mutating context between attempts.
            context["n2"] = NodeResult.single({"url": "https://seed-v2"})
            raise TimeoutError("transient")
        return {"url": url}

    monkeypatch.setattr(executor, "_run_node", fake_dispatch)

    context: dict[str, NodeResult] = {
        "n2": NodeResult.single({"url": "https://seed-v1"}),
    }
    node = Node(
        id="n1",
        type="navigate",
        label="read ctx",
        params={"url": "{{nodes.n2.output.url}}"},
        retry=RetryPolicy(max_attempts=2, backoff_ms=1),
    )

    async def noop_emit(*_a, **_k):
        pass

    async def run_invoke():
        # Mutate context after attempt 1 fails (inside fake_dispatch).
        outcome = await executor._invoke_node(
            node, noop_emit, context=context, input_items=[Item(json={})]
        )
        return outcome

    outcome = asyncio.run(run_invoke())
    assert outcome.kind == "completed"
    assert len(seen) == 2
    assert seen[0] == "https://seed-v1"
    assert seen[1] == "https://seed-v1"
