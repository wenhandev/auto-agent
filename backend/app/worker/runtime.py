"""Execute runs dispatched from the cloud worker hub."""

from __future__ import annotations

import asyncio
import base64
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlmodel import Session

from app.db.models import RunApproval
from app.db.session import engine
from app.schemas import Workflow
from app.services import runtime_engine as runtime_engine_svc
from app.worker import artifact_relay
from app.worker.run_inputs import materialize_input_files as worker_materialize_inputs


logger = logging.getLogger(__name__)

SendFn = Callable[[dict[str, Any]], Awaitable[None]]


async def _worker_finalize(
    run_id: str,
    _final_status: str,
    _last_payload: dict[str, Any],
    _terminal_error: Optional[str],
    *,
    browser_session_id: Optional[str],
    record_video: Optional[bool],
) -> None:
    from app.services import session_recording as session_rec_svc
    from app.tools.browser import end_run, stop_run_trace

    await stop_run_trace(run_id)
    if session_rec_svc.is_enabled(record_video):
        await session_rec_svc.finalize_recording(run_id)
    await end_run(run_id=run_id, browser_session_id=browser_session_id)


async def _worker_wait_approval(
    approval_id: str,
    *,
    abort_event: Optional[asyncio.Event] = None,
    resume_event: Optional[asyncio.Event] = None,
) -> RunApproval:
    """Poll DB (and optional resume signal) until approval is resolved."""
    from app.services import approvals as approvals_svc

    while True:
        if abort_event is not None and abort_event.is_set():
            raise approvals_svc.ApprovalWaitAborted()
        with Session(engine) as session:
            row = session.get(RunApproval, approval_id)
            if row is None:
                raise approvals_svc.ApprovalNotFound(f"approval {approval_id!r} not found")
            if row.decision is not None:
                return row
        if resume_event is not None:
            try:
                await asyncio.wait_for(resume_event.wait(), timeout=0.5)
                resume_event.clear()
                continue
            except asyncio.TimeoutError:
                continue
        await asyncio.sleep(0.5)


class WorkerRuntime:
    def __init__(
        self,
        *,
        send: SendFn,
        cloud_url: Optional[str] = None,
        worker_token: Optional[str] = None,
    ) -> None:
        self._send = send
        self._cloud_url = (cloud_url or "").rstrip("/")
        self._worker_token = worker_token or ""
        self._active: dict[str, asyncio.Event] = {}
        self._resume_events: dict[str, asyncio.Event] = {}
        self._stream_tasks: dict[str, asyncio.Task] = {}
        self._active_count = 0
        self._current_run_id: Optional[str] = None
        self._install_approval_wait()

    def _install_approval_wait(self) -> None:
        import app.services.approvals as approvals_svc

        runtime = self

        async def _wait(
            approval_id: str,
            *,
            abort_event: Optional[asyncio.Event] = None,
        ) -> RunApproval:
            resume_ev = runtime._resume_events.get(runtime._current_run_id or "")
            return await _worker_wait_approval(
                approval_id,
                abort_event=abort_event,
                resume_event=resume_ev,
            )

        approvals_svc.wait = _wait  # type: ignore[assignment]

    @property
    def active_runs(self) -> int:
        return self._active_count

    async def handle_execute(self, frame: dict[str, Any]) -> None:
        run_id = str(frame.get("run_id") or "")
        if not run_id:
            return
        workflow_raw = frame.get("workflow")
        if not isinstance(workflow_raw, dict):
            return
        workflow = Workflow.model_validate(workflow_raw)
        workflow_id = str(frame.get("workflow_id") or "")
        input_files = frame.get("input_files")
        if (
            isinstance(input_files, list)
            and workflow_id
            and self._cloud_url
            and self._worker_token
        ):
            try:
                await worker_materialize_inputs(
                    cloud_url=self._cloud_url,
                    token=self._worker_token,
                    run_id=run_id,
                    workflow_id=workflow_id,
                    input_files=input_files,
                )
            except Exception:
                logger.exception("worker input file materialize failed run=%s", run_id)
                await self._emit_run_event(
                    run_id,
                    {
                        "event": "run_failed",
                        "node_id": None,
                        "ts": _iso_now(),
                        "error": "failed to fetch run input files from cloud",
                    },
                )
                return

        abort_event = asyncio.Event()
        self._active[run_id] = abort_event
        self._resume_events[run_id] = asyncio.Event()
        self._active_count += 1
        self._current_run_id = run_id
        record_video = frame.get("record_video")

        async def finalize(
            rid: str,
            st: str,
            lp: dict[str, Any],
            te: Optional[str],
        ) -> None:
            await _worker_finalize(
                rid,
                st,
                lp,
                te,
                browser_session_id=None,
                record_video=record_video,
            )

        try:
            await runtime_engine_svc.execute_run(
                run_id=run_id,
                workflow=workflow,
                emit=lambda payload: self._emit_run_event(run_id, payload),
                abort_event=abort_event,
                browser_profile_id=frame.get("browser_profile_id"),
                trigger_namespace=frame.get("trigger_namespace") or {},
                params_namespace=frame.get("parameters") or {},
                totp_identifier=frame.get("totp_identifier"),
                record_video=record_video,
                workflow_id=workflow_id or None,
                finalize_run=finalize,
            )
        except Exception:
            logger.exception("worker execute failed run=%s", run_id)
            await self._emit_run_event(
                run_id,
                {
                    "event": "run_failed",
                    "node_id": None,
                    "ts": _iso_now(),
                    "error": "worker execution crashed",
                },
            )
        finally:
            await self._stop_stream(run_id)
            self._active.pop(run_id, None)
            self._resume_events.pop(run_id, None)
            self._active_count = max(0, self._active_count - 1)
            if self._current_run_id == run_id:
                self._current_run_id = None

    async def handle_abort(self, frame: dict[str, Any]) -> None:
        run_id = str(frame.get("run_id") or "")
        ev = self._active.get(run_id)
        if ev is not None:
            ev.set()

    async def handle_resume(self, frame: dict[str, Any]) -> None:
        run_id = str(frame.get("run_id") or "")
        ev = self._resume_events.get(run_id)
        if ev is not None:
            ev.set()

    async def handle_stream_subscribe(self, frame: dict[str, Any]) -> None:
        run_id = str(frame.get("run_id") or "")
        if not run_id or run_id in self._stream_tasks:
            return
        self._stream_tasks[run_id] = asyncio.create_task(self._stream_loop(run_id))

    async def handle_stream_unsubscribe(self, frame: dict[str, Any]) -> None:
        run_id = str(frame.get("run_id") or "")
        await self._stop_stream(run_id)

    async def _stop_stream(self, run_id: str) -> None:
        task = self._stream_tasks.pop(run_id, None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _stream_loop(self, run_id: str) -> None:
        from app.settings import settings
        from app.tools.browser import get_active_page

        seq = 0
        interval = max(0.1, 1.0 / max(settings.stream_fps, 1))
        try:
            while True:
                page = get_active_page(run_id)
                if page is not None:
                    try:
                        raw = await page.screenshot(type="jpeg", quality=settings.stream_jpeg_quality)
                        seq += 1
                        await self._send(
                            {
                                "type": "stream_frame",
                                "run_id": run_id,
                                "seq": seq,
                                "jpeg_base64": base64.b64encode(raw).decode("ascii"),
                                "width": settings.browser_viewport_width,
                                "height": settings.browser_viewport_height,
                            }
                        )
                    except Exception:
                        logger.debug("stream capture failed run=%s", run_id, exc_info=True)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return

    async def _emit_run_event(self, run_id: str, payload: dict[str, Any]) -> None:
        relayed = await artifact_relay.relay_event_artifacts(self._send, run_id, payload)
        seq = int(relayed.get("seq") or 0)
        await self._send(
            {
                "type": "run_event",
                "run_id": run_id,
                "seq": seq,
                "payload": relayed,
            }
        )

    def handle_artifact_upload_ack(self, frame: dict[str, Any]) -> None:
        artifact_relay.handle_ack(frame)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["WorkerRuntime"]
