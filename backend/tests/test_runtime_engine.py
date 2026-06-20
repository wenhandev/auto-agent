"""RuntimeEngine event sequence tests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.schemas import Edge, Node, Workflow
from app.services import runtime_engine as runtime_engine_svc


def _linear_workflow() -> Workflow:
    return Workflow(
        nodes=[
            Node(id="start", type="start", label="start"),
            Node(id="end", type="end", label="end"),
        ],
        edges=[Edge(id="e1", source="start", target="end")],
        start_id="start",
    )


@pytest.mark.asyncio
async def test_execute_run_emits_terminal_event_sequence() -> None:
    emitted: list[dict] = []

    async def fake_emit(payload: dict) -> None:
        emitted.append(payload)

    async def fake_run_workflow(workflow, emit_wrapped, **kwargs):
        await emit_wrapped({"event": "node_started", "node_id": "start", "ts": "t0"})
        await emit_wrapped({"event": "run_completed", "node_id": None, "ts": "t1"})

    abort = asyncio.Event()
    with patch("app.services.runtime_engine.begin_run", new=AsyncMock()), patch(
        "app.services.runtime_engine.start_run_trace", new=AsyncMock()
    ), patch("app.services.runtime_engine.run_workflow", side_effect=fake_run_workflow), patch(
        "app.services.runtime_engine._default_finalize", new=AsyncMock()
    ):
        result = await runtime_engine_svc.execute_run(
            run_id="run-seq-test",
            workflow=_linear_workflow(),
            emit=fake_emit,
            abort_event=abort,
        )

    assert result.get("event") == "run_completed"
    events = [p.get("event") for p in emitted]
    assert "node_started" in events
    assert events[-1] == "run_completed"
    for idx, payload in enumerate(emitted):
        assert payload.get("seq") == idx
        assert payload.get("run_id") == "run-seq-test"


@pytest.mark.asyncio
async def test_execute_run_persists_via_hook() -> None:
    persisted: list[tuple[int, dict]] = []

    def persist(_run_id: str, seq: int, payload: dict) -> None:
        persisted.append((seq, payload))

    async def fake_run_workflow(_workflow, emit_wrapped, **kwargs):
        await emit_wrapped({"event": "run_completed", "node_id": None, "ts": "t1"})

    with patch("app.services.runtime_engine.begin_run", new=AsyncMock()), patch(
        "app.services.runtime_engine.start_run_trace", new=AsyncMock()
    ), patch("app.services.runtime_engine.run_workflow", side_effect=fake_run_workflow), patch(
        "app.services.runtime_engine._default_finalize", new=AsyncMock()
    ):
        await runtime_engine_svc.execute_run(
            run_id="run-persist",
            workflow=_linear_workflow(),
            emit=AsyncMock(),
            abort_event=asyncio.Event(),
            persist_event=persist,
        )

    assert persisted
    assert persisted[-1][1]["event"] == "run_completed"
