"""Browser livestream hub and WebSocket transport tests (no real browser)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.db.models import Run, Workflow, WorkflowVersion
from app.db.session import engine, init_db
from app.main import app
from app.services import livestream as livestream_svc
from app.services.livestream import (
    LivestreamSession,
    STREAM_CLOSE_NOT_RUNNING,
    _ViewerConnection,
)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def running_run() -> str:
    init_db()
    with Session(engine) as session:
        wf = Workflow(name="livestream-test-wf")
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
            status="running",
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        return run.id


@pytest.fixture()
def completed_run() -> str:
    init_db()
    with Session(engine) as session:
        wf = Workflow(name="livestream-done-wf")
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


@pytest.fixture(autouse=True)
def _reset_livestream_hub() -> None:
    livestream_svc.hub._sessions.clear()
    yield
    livestream_svc.hub._sessions.clear()


@pytest.mark.asyncio
async def test_hub_starts_screencast_on_first_viewer_and_stops_on_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = AsyncMock()
    stopped = AsyncMock()

    async def fake_ensure(self: LivestreamSession) -> bool:
        await started()
        self._screencast_active = True
        return True

    async def fake_stop(self: LivestreamSession) -> None:
        await stopped()
        self._screencast_active = False

    monkeypatch.setattr(LivestreamSession, "_ensure_screencast", fake_ensure)
    monkeypatch.setattr(LivestreamSession, "_stop_screencast", fake_stop)

    session = LivestreamSession("run-1")
    ws1 = AsyncMock()
    ws2 = AsyncMock()

    await session.add_viewer(ws1)
    started.assert_awaited_once()
    stopped.assert_not_awaited()

    await session.add_viewer(ws2)
    started.assert_awaited_once()

    await session.remove_viewer(ws1)
    stopped.assert_not_awaited()

    await session.remove_viewer(ws2)
    stopped.assert_awaited_once()


@pytest.mark.asyncio
async def test_latest_wins_slot_never_queues_unbounded() -> None:
    ws = AsyncMock()

    async def slow_send(_payload: dict) -> None:
        await asyncio.sleep(0.05)

    ws.send_json = AsyncMock(side_effect=slow_send)

    viewer = _ViewerConnection(ws)
    await viewer.enqueue_frame({"seq": 1, "data": "a"})
    await viewer.enqueue_frame({"seq": 2, "data": "b"})
    await viewer.enqueue_frame({"seq": 3, "data": "c"})

    await asyncio.sleep(0.15)

    sent = [call.args[0] for call in ws.send_json.await_args_list]
    assert len(sent) <= 2
    assert sent[-1]["seq"] == 3
    assert viewer.pending is None


@pytest.mark.asyncio
async def test_stream_ended_emitted_on_run_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.livestream.settings.browser_headless", True)

    async def fake_ensure(self: LivestreamSession) -> bool:
        self._screencast_active = True
        return True

    monkeypatch.setattr(LivestreamSession, "_ensure_screencast", fake_ensure)

    session = LivestreamSession("run-ended")
    ws = AsyncMock()
    await session.add_viewer(ws)

    await session.notify_run_ended()

    ws.send_json.assert_awaited()
    last_call = ws.send_json.await_args_list[-1].args[0]
    assert last_call["type"] == "stream_ended"
    assert "ts" in last_call

    await session.notify_run_ended()
    assert ws.send_json.await_count == 1


def test_ws_stream_rejects_non_running_run(
    client: TestClient, completed_run: str
) -> None:
    with pytest.raises(Exception) as exc_info:
        with client.websocket_connect(f"/ws/stream/{completed_run}") as ws:
            ws.receive_json()

    assert str(STREAM_CLOSE_NOT_RUNNING) in str(exc_info.value) or getattr(
        exc_info.value, "code", None
    ) == STREAM_CLOSE_NOT_RUNNING


@pytest.mark.asyncio
async def test_session_injects_frames_to_viewer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ensure(self: LivestreamSession) -> bool:
        self._screencast_active = True
        return True

    monkeypatch.setattr(LivestreamSession, "_ensure_screencast", fake_ensure)

    session = LivestreamSession("inject-run")
    ws = AsyncMock()
    await session.add_viewer(ws)
    await session.inject_frame("/9j/frame1", width=640, height=480)
    await asyncio.sleep(0.05)
    await session.inject_frame("/9j/frame2", width=640, height=480)
    await asyncio.sleep(0.05)

    sent = [call.args[0] for call in ws.send_json.await_args_list]
    assert len(sent) == 2
    assert sent[0]["type"] == "frame"
    assert sent[0]["seq"] == 1
    assert sent[0]["width"] == 640
    assert sent[0]["height"] == 480
    assert sent[0]["data"] == "/9j/frame1"
    assert sent[1]["seq"] == 2
    assert sent[1]["data"] == "/9j/frame2"


@pytest.mark.asyncio
async def test_hub_notifies_stream_ended_on_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ensure(self: LivestreamSession) -> bool:
        self._screencast_active = True
        return True

    monkeypatch.setattr(LivestreamSession, "_ensure_screencast", fake_ensure)

    session = LivestreamSession("hub-ended")
    livestream_svc.hub._sessions["hub-ended"] = session
    ws = AsyncMock()
    await session.add_viewer(ws)

    await livestream_svc.on_run_ended("hub-ended")
    await asyncio.sleep(0.01)

    ws.send_json.assert_awaited()
    last_call = ws.send_json.await_args_list[-1].args[0]
    assert last_call["type"] == "stream_ended"
    assert "ts" in last_call


@pytest.mark.asyncio
async def test_hub_ingest_frame_from_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ensure(self: LivestreamSession) -> bool:
        self._screencast_active = True
        return True

    monkeypatch.setattr(LivestreamSession, "_ensure_screencast", fake_ensure)

    session = LivestreamSession("worker-run")
    livestream_svc.hub._sessions["worker-run"] = session
    ws = AsyncMock()
    await session.add_viewer(ws)

    await livestream_svc.ingest_frame(
        "worker-run",
        {"data": "/9j/workerframe", "width": 800, "height": 600, "seq": 7},
    )
    await asyncio.sleep(0.05)

    sent = [call.args[0] for call in ws.send_json.await_args_list]
    assert sent
    assert sent[-1]["type"] == "frame"
    assert sent[-1]["data"] == "/9j/workerframe"
    assert sent[-1]["seq"] == 7


@pytest.mark.asyncio
async def test_screencast_frame_ack_and_fanout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ensure(self: LivestreamSession) -> bool:
        self._screencast_active = True
        return True

    monkeypatch.setattr(LivestreamSession, "_ensure_screencast", fake_ensure)

    session = LivestreamSession("ack-run")
    ws = AsyncMock()
    await session.add_viewer(ws)

    fake_cdp = AsyncMock()
    session._cdp = fake_cdp

    await session._handle_screencast_frame(
        {
            "sessionId": 42,
            "data": "ZmFrZWpwZWc=",
            "metadata": {"deviceWidth": 1024, "deviceHeight": 768},
        }
    )
    await asyncio.sleep(0.05)

    fake_cdp.send.assert_awaited_once_with(
        "Page.screencastFrameAck", {"sessionId": 42}
    )
    ws.send_json.assert_awaited()
    payload = ws.send_json.await_args.args[0]
    assert payload["type"] == "frame"
    assert payload["seq"] == 1
    assert payload["width"] == 1024
    assert payload["height"] == 768
    assert payload["data"] == "ZmFrZWpwZWc="


@pytest.mark.asyncio
async def test_set_control_notifies_viewers_and_blocks_agent() -> None:
    session = LivestreamSession("control-run")
    livestream_svc.hub._sessions["control-run"] = session
    ws = AsyncMock()
    await session.add_viewer(ws)

    assert livestream_svc.user_has_control("control-run") is False
    await session.set_control("user")
    assert session.holder == "user"
    assert livestream_svc.user_has_control("control-run") is True

    sent = [call.args[0] for call in ws.send_json.await_args_list]
    assert sent[-1]["type"] == "control"
    assert sent[-1]["holder"] == "user"

    fake_cdp = AsyncMock()
    session._cdp = fake_cdp
    session._device = (200, 100)
    await session.dispatch_input(
        {"kind": "mouse", "event": "pressed", "x": 0.5, "y": 0.5, "clicks": 1}
    )
    fake_cdp.send.assert_awaited()
    args = fake_cdp.send.await_args.args
    assert args[0] == "Input.dispatchMouseEvent"
    assert args[1]["x"] == 100
    assert args[1]["y"] == 50

    await session.set_control("agent")
    assert livestream_svc.user_has_control("control-run") is False


@pytest.mark.asyncio
async def test_handle_viewer_set_control_message() -> None:
    session = LivestreamSession("msg-run")
    await session.handle_viewer_message('{"type":"set_control","holder":"user"}')
    assert session.holder == "user"
