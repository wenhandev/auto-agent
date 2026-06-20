from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import WebSocket, WebSocketDisconnect
from sqlmodel import Session

from app.db.models import Run
from app.db.session import engine
from app.settings import settings

logger = logging.getLogger(__name__)

# Application-specific WebSocket close code (4400–4999 range).
STREAM_CLOSE_NOT_RUNNING = 4404


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_run_status(run_id: str) -> Optional[str]:
    with Session(engine) as session:
        run = session.get(Run, run_id)
        return run.status if run else None


def _is_worker_run(run_id: str) -> bool:
    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None:
            return False
        return getattr(run, "execution_mode", "cloud") == "worker"


class _ViewerConnection:
    """One stream viewer with a single latest-wins pending frame slot."""

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.pending: Optional[dict[str, Any]] = None
        self._send_task: Optional[asyncio.Task] = None
        self._closed = False

    async def enqueue_frame(self, frame: dict[str, Any]) -> None:
        self.pending = frame
        if self._send_task is None or self._send_task.done():
            self._send_task = asyncio.create_task(self._drain())

    async def _drain(self) -> None:
        while self.pending is not None and not self._closed:
            frame = self.pending
            self.pending = None
            try:
                await self.ws.send_json({"type": "frame", **frame})
            except Exception:
                self._closed = True
                break

    async def send_control(self, msg: dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            await self.ws.send_json(msg)
        except Exception:
            self._closed = True

    async def close(self) -> None:
        self._closed = True
        if self._send_task is not None and not self._send_task.done():
            self._send_task.cancel()
            try:
                await self._send_task
            except asyncio.CancelledError:
                pass


class LivestreamSession:
    """One CDP screencast producer fanning out to N viewers for a run."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.viewers: dict[int, _ViewerConnection] = {}
        self._seq = 0
        self._screencast_active = False
        self._cdp: Any = None
        self._lock = asyncio.Lock()
        self._ended = False
        self._retry_task: Optional[asyncio.Task] = None

    @property
    def viewer_count(self) -> int:
        return len(self.viewers)

    async def _notify_viewers(self, msg: dict[str, Any]) -> None:
        for viewer in list(self.viewers.values()):
            await viewer.send_control(msg)

    async def add_viewer(self, ws: WebSocket) -> _ViewerConnection:
        async with self._lock:
            viewer = _ViewerConnection(ws)
            self.viewers[id(ws)] = viewer
            if not self._screencast_active and not self._ended:
                if _is_worker_run(self.run_id):
                    from app.services import worker_hub

                    await worker_hub.notify_stream_subscribe(self.run_id)
                else:
                    await self._ensure_screencast()
            return viewer

    async def remove_viewer(self, ws: WebSocket) -> None:
        async with self._lock:
            viewer = self.viewers.pop(id(ws), None)
            if viewer is not None:
                await viewer.close()
            if self.viewer_count == 0:
                self._cancel_retry()
                if _is_worker_run(self.run_id):
                    from app.services import worker_hub

                    await worker_hub.notify_stream_unsubscribe(self.run_id)
                elif self._screencast_active:
                    await self._stop_screencast()

    def _cancel_retry(self) -> None:
        if self._retry_task is not None and not self._retry_task.done():
            self._retry_task.cancel()
        self._retry_task = None

    def _schedule_screencast_retry(self) -> None:
        if self._retry_task is not None and not self._retry_task.done():
            return
        self._retry_task = asyncio.create_task(self._screencast_retry_loop())

    async def _screencast_retry_loop(self) -> None:
        delay = 0.3
        try:
            for _ in range(100):
                await asyncio.sleep(delay)
                if self._ended or self.viewer_count == 0:
                    return
                if self._screencast_active:
                    return
                if await self._ensure_screencast():
                    return
                delay = min(delay * 1.2, 1.0)
            if (
                self.viewer_count > 0
                and not self._screencast_active
                and not self._ended
            ):
                await self._notify_viewers(
                    {"type": "stream_unavailable", "ts": _utcnow_iso()}
                )
        except asyncio.CancelledError:
            return

    async def _ensure_screencast(self) -> bool:
        from app.services.browser_visual import skip_optional_page_screenshots

        if self._ended or self._screencast_active:
            return self._screencast_active

        if skip_optional_page_screenshots():
            await self._notify_viewers(
                {"type": "stream_headed", "ts": _utcnow_iso()}
            )
            logger.debug(
                "livestream: headed mode — screencast disabled run=%s", self.run_id
            )
            return False

        from app.tools.browser import get_active_page

        page = get_active_page(self.run_id)
        if page is None:
            await self._notify_viewers(
                {"type": "stream_waiting", "ts": _utcnow_iso()}
            )
            logger.debug("livestream: waiting for browser page run=%s", self.run_id)
            self._schedule_screencast_retry()
            return False

        if await self._attach_screencast(page):
            return True

        self._schedule_screencast_retry()
        return False

    async def _attach_screencast(self, page: Any) -> bool:
        if self._screencast_active:
            return True
        try:
            cdp = await page.context.new_cdp_session(page)
            self._cdp = cdp

            every_nth = max(1, round(60 / max(settings.stream_fps, 1)))

            def on_screencast_frame(params: dict[str, Any]) -> None:
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._handle_screencast_frame(params))
                except RuntimeError:
                    from app.services import runs as run_svc

                    if run_svc._main_loop is not None:
                        run_svc._main_loop.call_soon_threadsafe(
                            lambda p=params: run_svc._main_loop.create_task(  # type: ignore[union-attr]
                                self._handle_screencast_frame(p)
                            )
                        )

            cdp.on("Page.screencastFrame", on_screencast_frame)

            await cdp.send(
                "Page.startScreencast",
                {
                    "format": "jpeg",
                    "quality": settings.stream_jpeg_quality,
                    "maxWidth": settings.stream_max_width,
                    "maxHeight": settings.stream_max_width,
                    "everyNthFrame": every_nth,
                },
            )
            self._screencast_active = True
            self._cancel_retry()
            logger.debug("livestream screencast started run=%s", self.run_id)
            return True
        except Exception:
            logger.exception("livestream screencast start failed run=%s", self.run_id)
            return False

    async def _start_screencast(self) -> None:
        await self._ensure_screencast()

    async def _handle_screencast_frame(self, params: dict[str, Any]) -> None:
        session_id = params.get("sessionId")
        if self._cdp is not None and session_id is not None:
            try:
                await self._cdp.send(
                    "Page.screencastFrameAck", {"sessionId": session_id}
                )
            except Exception:
                pass

        metadata = params.get("metadata") or {}
        self._seq += 1
        frame = {
            "ts": _utcnow_iso(),
            "seq": self._seq,
            "width": metadata.get("deviceWidth", 0),
            "height": metadata.get("deviceHeight", 0),
            "data": params.get("data", ""),
        }
        await self._fanout_frame(frame)

    async def _fanout_frame(self, frame: dict[str, Any]) -> None:
        for viewer in list(self.viewers.values()):
            await viewer.enqueue_frame(frame)

    async def inject_frame(
        self,
        data: str,
        *,
        width: int = 800,
        height: int = 600,
    ) -> None:
        """Push a frame without CDP (used by tests)."""
        self._seq += 1
        frame = {
            "ts": _utcnow_iso(),
            "seq": self._seq,
            "width": width,
            "height": height,
            "data": data,
        }
        await self._fanout_frame(frame)

    async def _stop_screencast(self) -> None:
        if self._cdp is not None:
            try:
                await self._cdp.send("Page.stopScreencast")
            except Exception:
                pass
            try:
                await self._cdp.detach()
            except Exception:
                pass
            self._cdp = None
        self._screencast_active = False
        logger.debug("livestream screencast stopped run=%s", self.run_id)

    async def notify_run_ended(self) -> None:
        async with self._lock:
            if self._ended:
                return
            self._ended = True
            self._cancel_retry()
            if self._screencast_active:
                await self._stop_screencast()
            msg = {"type": "stream_ended", "ts": _utcnow_iso()}
            for viewer in list(self.viewers.values()):
                await viewer.send_control(msg)


class LivestreamHub:
    def __init__(self) -> None:
        self._sessions: dict[str, LivestreamSession] = {}
        self._lock = asyncio.Lock()

    def get_session(self, run_id: str) -> Optional[LivestreamSession]:
        return self._sessions.get(run_id)

    async def _get_or_create_session(self, run_id: str) -> LivestreamSession:
        async with self._lock:
            session = self._sessions.get(run_id)
            if session is None:
                session = LivestreamSession(run_id)
                self._sessions[run_id] = session
            return session

    async def _maybe_remove_session(self, run_id: str, session: LivestreamSession) -> None:
        if session.viewer_count > 0:
            return
        async with self._lock:
            if self._sessions.get(run_id) is session and session.viewer_count == 0:
                self._sessions.pop(run_id, None)

    async def handle_connection(self, run_id: str, ws: WebSocket) -> None:
        await ws.accept()
        status = get_run_status(run_id)
        if status != "running":
            reason = f"run is {status or 'not found'}, not running"
            await ws.close(code=STREAM_CLOSE_NOT_RUNNING, reason=reason)
            return

        session = await self._get_or_create_session(run_id)
        await session.add_viewer(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("livestream viewer error run=%s", run_id)
        finally:
            await session.remove_viewer(ws)
            await self._maybe_remove_session(run_id, session)

    async def on_run_ended(self, run_id: str) -> None:
        session = self._sessions.get(run_id)
        if session is not None:
            await session.notify_run_ended()

    async def ingest_frame(self, run_id: str, frame: dict[str, Any]) -> None:
        """Ingest a JPEG frame uploaded by a worker runtime."""
        session = await self._get_or_create_session(run_id)
        data = frame.get("data") or ""
        if not data:
            return
        seq = frame.get("seq")
        if isinstance(seq, int):
            session._seq = max(session._seq, seq)
        else:
            session._seq += 1
        out = {
            "ts": _utcnow_iso(),
            "seq": session._seq if not isinstance(seq, int) else seq,
            "width": int(frame.get("width") or 800),
            "height": int(frame.get("height") or 600),
            "data": data,
        }
        await session._fanout_frame(out)


hub = LivestreamHub()

handle_connection = hub.handle_connection
on_run_ended = hub.on_run_ended
ingest_frame = hub.ingest_frame

__all__ = [
    "LivestreamHub",
    "LivestreamSession",
    "STREAM_CLOSE_NOT_RUNNING",
    "get_run_status",
    "handle_connection",
    "hub",
    "ingest_frame",
    "on_run_ended",
]
