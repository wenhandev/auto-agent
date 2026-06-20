"""Local workflow runs for the desktop sidecar."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import httpx

from app.schemas import Workflow
from app.services import runtime_engine as runtime_engine_svc
from app.worker import credentials as cred_svc
from app.worker.local_llm import require_configured


logger = logging.getLogger(__name__)

RUNS_DIR = Path.home() / ".auto-agent-worker" / "runs"
RUNS_INDEX = RUNS_DIR / "index.json"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_index() -> list[dict[str, Any]]:
    if not RUNS_INDEX.is_file():
        return []
    try:
        data = json.loads(RUNS_INDEX.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _save_index(rows: list[dict[str, Any]]) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_INDEX.write_text(json.dumps(rows[-100:], indent=2), encoding="utf-8")


def _events_path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.events.jsonl"


@dataclass
class LocalRunManager:
    _active: dict[str, asyncio.Event] = field(default_factory=dict)
    _tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    _subscribers: dict[str, list[asyncio.Queue[dict[str, Any] | None]]] = field(
        default_factory=dict
    )
    _stream_tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def list_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = _load_index()
        return list(reversed(rows[-limit:]))

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        for row in reversed(_load_index()):
            if row.get("id") == run_id:
                return row
        return None

    async def start_run(
        self,
        *,
        workflow: Workflow,
        workflow_id: Optional[str] = None,
        parameters: Optional[dict[str, Any]] = None,
        trigger_namespace: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        require_configured()
        run_id = f"local_{uuid.uuid4().hex[:12]}"
        meta = {
            "id": run_id,
            "workflow_id": workflow_id,
            "status": "running",
            "started_at": _utcnow(),
            "finished_at": None,
        }
        rows = _load_index()
        rows.append(meta)
        _save_index(rows)

        abort_event = asyncio.Event()
        self._active[run_id] = abort_event
        self._tasks[run_id] = asyncio.create_task(
            self._execute(
                run_id=run_id,
                workflow=workflow,
                workflow_id=workflow_id,
                parameters=parameters or {},
                trigger_namespace=trigger_namespace or {},
                abort_event=abort_event,
            )
        )
        return meta

    async def abort_run(self, run_id: str) -> bool:
        ev = self._active.get(run_id)
        if ev is None:
            return False
        ev.set()
        return True

    async def subscribe_events(self, run_id: str) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=256)
        self._subscribers.setdefault(run_id, []).append(queue)
        for line in _read_persisted_events(run_id):
            yield line
        meta = self.get_run(run_id)
        if meta and meta.get("status") != "running":
            return
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            subs = self._subscribers.get(run_id, [])
            if queue in subs:
                subs.remove(queue)

    async def _execute(
        self,
        *,
        run_id: str,
        workflow: Workflow,
        workflow_id: Optional[str],
        parameters: dict[str, Any],
        trigger_namespace: dict[str, Any],
        abort_event: asyncio.Event,
    ) -> None:
        from app.worker.runtime import _worker_finalize

        self._stream_tasks[run_id] = asyncio.create_task(self._stream_loop(run_id))

        async def finalize(
            rid: str,
            st: str,
            _lp: dict[str, Any],
            _te: Optional[str],
        ) -> None:
            await _worker_finalize(
                rid,
                st,
                _lp,
                _te,
                browser_session_id=None,
                record_video=None,
            )

        terminal = "failed"
        try:
            last = await runtime_engine_svc.execute_run(
                run_id=run_id,
                workflow=workflow,
                emit=lambda payload: self._emit(run_id, payload),
                abort_event=abort_event,
                trigger_namespace=trigger_namespace,
                params_namespace=parameters,
                workflow_id=workflow_id,
                finalize_run=finalize,
            )
            event = str(last.get("event") or "")
            terminal_map = {
                "run_completed": "completed",
                "run_completed_with_errors": "completed_with_errors",
                "run_failed": "failed",
                "run_aborted": "aborted",
                "run_rejected": "rejected",
            }
            terminal = terminal_map.get(event, "completed")
        except Exception as exc:
            logger.exception("local run failed run=%s", run_id)
            await self._emit(
                run_id,
                {
                    "event": "run_failed",
                    "node_id": None,
                    "ts": _utcnow(),
                    "error": str(exc),
                },
            )
            terminal = "failed"
        finally:
            await self._stop_stream(run_id)
            self._active.pop(run_id, None)
            self._tasks.pop(run_id, None)
            self._update_status(run_id, terminal)
            await self._broadcast(run_id, None)

    async def _emit(self, run_id: str, payload: dict[str, Any]) -> None:
        line = {**payload, "run_id": run_id}
        _append_event(run_id, line)
        await self._broadcast(run_id, line)

    async def _broadcast(
        self, run_id: str, payload: Optional[dict[str, Any]]
    ) -> None:
        for queue in list(self._subscribers.get(run_id, [])):
            try:
                queue.put_nowait(payload)  # type: ignore[arg-type]
            except asyncio.QueueFull:
                pass

    def _update_status(self, run_id: str, status: str) -> None:
        rows = _load_index()
        for row in rows:
            if row.get("id") == run_id:
                row["status"] = status
                row["finished_at"] = _utcnow()
                break
        _save_index(rows)

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
                        raw = await page.screenshot(
                            type="jpeg", quality=settings.stream_jpeg_quality
                        )
                        seq += 1
                        frame = {
                            "type": "frame",
                            "seq": seq,
                            "data": base64.b64encode(raw).decode("ascii"),
                            "width": settings.browser_viewport_width,
                            "height": settings.browser_viewport_height,
                            "ts": _utcnow(),
                        }
                        for queue in list(self._subscribers.get(run_id, [])):
                            try:
                                queue.put_nowait({"type": "stream_frame", **frame})
                            except asyncio.QueueFull:
                                pass
                    except Exception:
                        logger.debug("local stream capture failed run=%s", run_id, exc_info=True)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return

    async def _stop_stream(self, run_id: str) -> None:
        task = self._stream_tasks.pop(run_id, None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def _append_event(run_id: str, payload: dict[str, Any]) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    with _events_path(run_id).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, default=str) + "\n")


def _read_persisted_events(run_id: str) -> list[dict[str, Any]]:
    path = _events_path(run_id)
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def fetch_cloud_workflow(
    *, cloud_url: str, web_token: str, workflow_id: str
) -> tuple[Workflow, str]:
    with httpx.Client(timeout=30.0) as client:
        res = client.get(
            f"{cloud_url.rstrip('/')}/api/workflows/{workflow_id}",
            headers={"Authorization": f"Bearer {web_token}"},
        )
        res.raise_for_status()
        data = res.json()
    version = data.get("current_version") or {}
    workflow_raw = version.get("workflow")
    if not isinstance(workflow_raw, dict):
        raise ValueError("workflow has no current version")
    return Workflow.model_validate(workflow_raw), workflow_id


def cloud_get(path: str) -> Any:
    saved = cred_svc.load_credentials() or {}
    cloud_url = str(saved.get("cloud_url") or "").rstrip("/")
    token = saved.get("web_session_token")
    if not cloud_url or not token:
        raise RuntimeError("cloud session not configured")
    with httpx.Client(timeout=30.0) as client:
        res = client.get(
            f"{cloud_url}{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
        res.raise_for_status()
        return res.json()


def cloud_post(path: str, body: dict[str, Any]) -> Any:
    saved = cred_svc.load_credentials() or {}
    cloud_url = str(saved.get("cloud_url") or "").rstrip("/")
    token = saved.get("web_session_token")
    if not cloud_url or not token:
        raise RuntimeError("cloud session not configured")
    with httpx.Client(timeout=60.0) as client:
        res = client.post(
            f"{cloud_url}{path}",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )
        res.raise_for_status()
        return res.json()


__all__ = [
    "LocalRunManager",
    "cloud_get",
    "cloud_post",
    "fetch_cloud_workflow",
]
