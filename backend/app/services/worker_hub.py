"""Cloud-side worker connection hub and job dispatch."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import WebSocket
from sqlmodel import Session

from app.db.models import Run, Worker, WorkflowVersion
from app.db.session import engine
from app.services import run_inputs as run_input_svc
from app.services import workflow_parameters as param_svc
from app.services import workflows as workflow_svc


logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WorkerConnection:
    worker_id: str
    org_id: str
    websocket: WebSocket
    active_runs: int = 0
    max_concurrent_runs: int = 1
    environment_status: str = "unknown"
    capabilities: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=lambda: ["default"])
    approval_status: str = "approved"


_connections: dict[str, WorkerConnection] = {}
_worker_running: set[str] = set()
_run_to_worker: dict[str, str] = {}
_lock = asyncio.Lock()


def is_worker_assignable(
    conn: WorkerConnection,
    *,
    worker_pool: Optional[str],
    run_needs_headed: bool = False,
) -> bool:
    if conn.approval_status != "approved":
        return False
    if conn.environment_status == "not_ready":
        return False
    if conn.environment_status not in ("ready", "degraded", "unknown"):
        return False
    if conn.environment_status == "degraded":
        caps = conn.capabilities or {}
        if not caps.get("chromium", True):
            return False
        if run_needs_headed and not caps.get("headed_display", True):
            return False
    if conn.active_runs >= conn.max_concurrent_runs:
        return False
    pool = worker_pool or "default"
    return pool in conn.tags or "default" in conn.tags


def _run_needs_headed(run_id: str) -> bool:
    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None:
            return False
        if run.record_video:
            return True
    from app.settings import settings

    return not settings.browser_headless


def has_assignable_worker(
    org_id: Optional[str],
    *,
    worker_pool: Optional[str],
    pinned_worker_id: Optional[str] = None,
    run_needs_headed: bool = False,
) -> bool:
    for conn in _connections.values():
        if org_id and conn.org_id != org_id:
            continue
        if pinned_worker_id and conn.worker_id != pinned_worker_id:
            continue
        if is_worker_assignable(
            conn,
            worker_pool=worker_pool,
            run_needs_headed=run_needs_headed,
        ):
            return True
    return False


def count_online_workers(org_id: Optional[str]) -> int:
    return sum(1 for c in _connections.values() if not org_id or c.org_id == org_id)


async def register_connection(
    worker_id: str,
    org_id: str,
    ws: WebSocket,
    *,
    max_concurrent_runs: int = 1,
    tags: Optional[list[str]] = None,
    environment: Optional[dict[str, Any]] = None,
) -> WorkerConnection:
    env = environment or {}
    from app.db.models import Worker
    from app.services import workers as worker_svc

    approval_status = "approved"
    with Session(engine) as session:
        worker_row = session.get(Worker, worker_id)
        if worker_row is not None:
            approval_status = worker_svc.effective_approval_status(worker_row)

    # Pending/rejected workers may connect for heartbeats and admin visibility;
    # dispatch is blocked in is_worker_assignable until approval_status=approved.
    conn = WorkerConnection(
        worker_id=worker_id,
        org_id=org_id,
        websocket=ws,
        max_concurrent_runs=max(1, max_concurrent_runs),
        environment_status=str(env.get("environment_status") or "unknown"),
        capabilities=dict(env.get("capabilities") or {}),
        tags=list(tags or ["default"]),
        approval_status=approval_status,
    )
    async with _lock:
        old = _connections.get(worker_id)
        if old is not None and old.websocket is not ws:
            try:
                await old.websocket.close(code=4000)
            except Exception:
                pass
        _connections[worker_id] = conn
    from app.services import workers as worker_svc

    with Session(engine) as session:
        worker_svc.set_worker_status(session, worker_id, "online")
        if environment:
            worker_svc.update_worker_environment(session, worker_id, environment)
    from app.services import runs as run_svc

    run_svc.wakeup_dispatcher()
    return conn


async def unregister_connection(worker_id: str) -> None:
    async with _lock:
        _connections.pop(worker_id, None)
    from app.services import workers as worker_svc

    with Session(engine) as session:
        worker_svc.set_worker_status(session, worker_id, "offline")


async def send_frame(worker_id: str, frame: dict[str, Any]) -> bool:
    conn = _connections.get(worker_id)
    if conn is None:
        return False
    try:
        await conn.websocket.send_json(frame)
        return True
    except Exception:
        logger.exception("send_frame failed worker=%s", worker_id)
        return False


async def handle_heartbeat(worker_id: str, payload: dict[str, Any]) -> None:
    conn = _connections.get(worker_id)
    if conn is None:
        return
    conn.active_runs = int(payload.get("active_runs") or conn.active_runs)
    env = payload.get("environment")
    if isinstance(env, dict):
        conn.environment_status = str(env.get("environment_status") or conn.environment_status)
        caps = env.get("capabilities")
        if isinstance(caps, dict):
            conn.capabilities = caps
        from app.services import workers as worker_svc

        with Session(engine) as session:
            worker_svc.update_worker_environment(session, worker_id, env)
            worker_row = session.get(Worker, worker_id)
            if worker_row is not None:
                conn.approval_status = worker_svc.effective_approval_status(worker_row)


async def _release_run(run_id: str) -> None:
    wid = _run_to_worker.get(run_id)
    async with _lock:
        _worker_running.discard(run_id)
        _run_to_worker.pop(run_id, None)
    if wid and wid in _connections:
        _connections[wid].active_runs = max(0, _connections[wid].active_runs - 1)
    from app.services import runs as run_svc

    run_svc.wakeup_dispatcher()


async def handle_artifact_upload(worker_id: str, frame: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Persist artifact bytes relayed from a worker; returns ack payload."""
    from app.services import artifacts as artifact_svc
    import base64

    run_id = str(frame.get("run_id") or "")
    upload_id = str(frame.get("upload_id") or "")
    kind = str(frame.get("kind") or "")
    if not run_id or not upload_id or not kind:
        return None
    if _run_to_worker.get(run_id) != worker_id:
        logger.warning(
            "artifact_upload from wrong worker run=%s worker=%s", run_id, worker_id
        )
        return None
    if kind not in artifact_svc.ARTIFACT_KINDS:
        logger.warning("artifact_upload invalid kind=%s run=%s", kind, run_id)
        return None
    raw_b64 = frame.get("data_base64") or ""
    if not raw_b64:
        return None
    try:
        data = base64.b64decode(raw_b64)
    except Exception:
        logger.warning("artifact_upload invalid base64 run=%s upload=%s", run_id, upload_id)
        return None
    row = artifact_svc.store_bytes(
        run_id,
        kind,
        data,
        content_type=frame.get("content_type"),
        node_id=frame.get("node_id"),
        step_index=frame.get("step_index"),
        filename=frame.get("filename"),
        note=frame.get("note"),
    )
    return {
        "type": "artifact_upload_ack",
        "run_id": run_id,
        "upload_id": upload_id,
        "artifact_id": row.id,
    }


async def handle_run_event(worker_id: str, payload: dict[str, Any]) -> None:
    from app.services import runs as run_svc

    run_id = str(payload.get("run_id") or "")
    seq = int(payload.get("seq") or 0)
    event_payload = payload.get("payload")
    if not run_id or not isinstance(event_payload, dict):
        return
    if _run_to_worker.get(run_id) != worker_id:
        logger.warning("run_event from wrong worker run=%s worker=%s", run_id, worker_id)
        return
    await run_svc.ingest_worker_event(run_id, seq, event_payload)
    if event_payload.get("event") in (
        "run_completed",
        "run_completed_with_errors",
        "run_failed",
        "run_aborted",
        "run_rejected",
    ):
        await _release_run(run_id)


def _build_execute_payload(run_id: str) -> Optional[dict[str, Any]]:
    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None or run.status != "queued":
            return None
        version = session.get(WorkflowVersion, run.workflow_version_id)
        if version is None:
            return None
        try:
            workflow = workflow_svc.load_workflow_schema(version)
        except Exception:
            return None
        params = param_svc.load_resolved_parameters_json(run.parameters_json)
        input_files = run_input_svc.load_input_files_for_worker(run_id, params)
        trigger_ns: dict[str, Any] = {}
        if run.trigger_context_json:
            try:
                ctx = json.loads(run.trigger_context_json)
                if isinstance(ctx, dict):
                    trigger_ns = {
                        "kind": ctx.get("kind") or run.source,
                        "id": ctx.get("trigger_id") or run.trigger_id,
                        "headers": ctx.get("headers") or {},
                    }
            except Exception:
                pass
        run.status = "running"
        run.started_at = _utcnow()
        run.worker_assigned_at = _utcnow()
        session.add(run)
        session.commit()
        return {
            "type": "execute_run",
            "run_id": run_id,
            "workflow_id": run.workflow_id,
            "workflow": workflow.model_dump(),
            "parameters": params or {},
            "input_files": input_files,
            "trigger_namespace": trigger_ns,
            "browser_profile_id": run.browser_profile_id,
            "totp_identifier": run.totp_identifier,
            "record_video": run.record_video,
        }


async def try_assign_run(run_id: str) -> bool:
    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None or run.execution_mode != "worker":
            return False
        if run.status != "queued":
            return False
        org_id = run.org_id
        worker_pool = run.worker_pool or "default"
        pinned = run.worker_id
        needs_headed = _run_needs_headed(run_id)

    candidates: list[WorkerConnection] = []
    with Session(engine) as session:
        from app.services import workers as worker_svc

        for conn in _connections.values():
            if org_id and conn.org_id != org_id:
                continue
            if pinned and conn.worker_id != pinned:
                continue
            worker_row = session.get(Worker, conn.worker_id)
            if worker_row is not None:
                conn.approval_status = worker_svc.effective_approval_status(worker_row)
            if is_worker_assignable(
                conn,
                worker_pool=worker_pool,
                run_needs_headed=needs_headed,
            ):
                candidates.append(conn)
    if not candidates:
        return False
    candidates.sort(key=lambda c: c.active_runs)
    conn = candidates[0]
    payload = _build_execute_payload(run_id)
    if payload is None:
        return False
    ok = await send_frame(conn.worker_id, payload)
    if not ok:
        return False
    async with _lock:
        _worker_running.add(run_id)
        _run_to_worker[run_id] = conn.worker_id
        conn.active_runs += 1
    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is not None:
            run.worker_id = conn.worker_id
            session.add(run)
            session.commit()
    from app.services import runs as run_svc

    run_svc.remove_from_dispatcher_queue(run_id)
    return True


async def dispatch_queued_worker_runs() -> None:
    from app.services import runs as run_svc

    for run_id in run_svc.list_queued_worker_run_ids():
        if run_id in _worker_running:
            continue
        await try_assign_run(run_id)


async def request_abort_on_worker(run_id: str) -> None:
    wid = _run_to_worker.get(run_id)
    if wid:
        await send_frame(wid, {"type": "abort", "run_id": run_id})


async def request_resume_on_worker(run_id: str) -> None:
    wid = _run_to_worker.get(run_id)
    if wid:
        await send_frame(wid, {"type": "resume_run", "run_id": run_id})


async def notify_stream_subscribe(run_id: str) -> None:
    wid = _run_to_worker.get(run_id)
    if wid:
        await send_frame(wid, {"type": "stream_subscribe", "run_id": run_id})


async def notify_stream_unsubscribe(run_id: str) -> None:
    wid = _run_to_worker.get(run_id)
    if wid:
        await send_frame(wid, {"type": "stream_unsubscribe", "run_id": run_id})


async def handle_stream_frame(worker_id: str, payload: dict[str, Any]) -> None:
    from app.services import livestream as livestream_svc

    run_id = str(payload.get("run_id") or "")
    if not run_id or _run_to_worker.get(run_id) != worker_id:
        logger.warning("stream_frame from wrong worker run=%s worker=%s", run_id, worker_id)
        return
    data = payload.get("jpeg_base64") or payload.get("data") or ""
    if not data:
        return
    await livestream_svc.ingest_frame(
        run_id,
        {
            "data": data,
            "width": int(payload.get("width") or 800),
            "height": int(payload.get("height") or 600),
            "seq": payload.get("seq"),
        },
    )


def reset_for_tests() -> None:
    _connections.clear()
    _worker_running.clear()
    _run_to_worker.clear()


def active_run_count(worker_id: str) -> int:
    conn = _connections.get(worker_id)
    if conn is not None:
        return conn.active_runs
    return sum(1 for rid, wid in _run_to_worker.items() if wid == worker_id)


__all__ = [
    "WorkerConnection",
    "register_connection",
    "unregister_connection",
    "handle_heartbeat",
    "handle_artifact_upload",
    "handle_run_event",
    "handle_stream_frame",
    "dispatch_queued_worker_runs",
    "try_assign_run",
    "request_abort_on_worker",
    "request_resume_on_worker",
    "notify_stream_subscribe",
    "notify_stream_unsubscribe",
    "is_worker_assignable",
    "has_assignable_worker",
    "count_online_workers",
    "active_run_count",
    "reset_for_tests",
]
