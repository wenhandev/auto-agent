from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from app.db.models import Run, RunEvent, Workflow, WorkflowVersion
from app.db.session import engine
from app.services.workflows import load_workflow_schema


logger = logging.getLogger(__name__)


_queues: dict[str, deque[str]] = {}
_workflow_tasks: dict[str, asyncio.Task] = {}
_abort_events: dict[str, asyncio.Event] = {}
_subscribers: dict[str, list[asyncio.Queue]] = {}
_loop_lock = asyncio.Lock()
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def _schedule(coro) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
        return
    except RuntimeError:
        pass
    if _main_loop is not None:
        asyncio.run_coroutine_threadsafe(coro, _main_loop)
    else:
        logger.warning("no running loop and no main loop registered; coroutine dropped")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def subscribe(run_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.setdefault(run_id, []).append(q)
    return q


def unsubscribe(run_id: str, q: asyncio.Queue) -> None:
    subs = _subscribers.get(run_id)
    if not subs:
        return
    try:
        subs.remove(q)
    except ValueError:
        pass
    if not subs:
        _subscribers.pop(run_id, None)


def _fanout(run_id: str, payload: dict) -> None:
    subs = list(_subscribers.get(run_id, ()))
    if not subs:
        return

    def _put_all() -> None:
        for q in subs:
            try:
                q.put_nowait(payload)
            except Exception:
                logger.exception("fanout failed run=%s", run_id)

    try:
        asyncio.get_running_loop()
        _put_all()
    except RuntimeError:
        if _main_loop is not None:
            _main_loop.call_soon_threadsafe(_put_all)
        else:
            logger.warning("fanout dropped (no loop) run=%s", run_id)


def fetch_prior_events(run_id: str) -> list[dict]:
    with Session(engine) as session:
        rows = session.exec(
            select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
        ).all()
    return [json.loads(r.payload_json) for r in rows]


def is_terminal(payload: dict) -> bool:
    return payload.get("event") in ("run_completed", "run_failed", "run_aborted")


def enqueue_run(
    workflow_id: str,
    session: Session,
    *,
    version_id: Optional[str] = None,
    source: str = "manual",
    trigger_id: Optional[str] = None,
    trigger_context: Optional[dict] = None,
) -> Run:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise ValueError(f"workflow {workflow_id!r} not found")
    vid = version_id or workflow.current_version_id
    if vid is None:
        raise ValueError(f"workflow {workflow_id!r} has no version")
    version = session.get(WorkflowVersion, vid)
    if version is None:
        raise ValueError(f"workflow version {vid!r} not found")

    ctx_json: Optional[str] = None
    if trigger_context is not None:
        try:
            ctx_json = json.dumps(trigger_context, ensure_ascii=False, default=str)
        except Exception:
            logger.exception("failed to serialize trigger_context for workflow=%s", workflow_id)
            ctx_json = None

    run = Run(
        workflow_id=workflow_id,
        workflow_version_id=vid,
        status="queued",
        queued_at=_utcnow(),
        source=source,
        trigger_id=trigger_id,
        trigger_context_json=ctx_json,
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    _queues.setdefault(workflow_id, deque()).append(run.id)
    _schedule(_ensure_loop(workflow_id))
    return run


async def _ensure_loop(workflow_id: str) -> None:
    async with _loop_lock:
        task = _workflow_tasks.get(workflow_id)
        if task is None or task.done():
            _workflow_tasks[workflow_id] = asyncio.create_task(
                _dequeue_loop(workflow_id)
            )


async def _dequeue_loop(workflow_id: str) -> None:
    try:
        while True:
            q = _queues.get(workflow_id)
            if not q:
                return
            run_id = q.popleft()
            try:
                await _drive_run(run_id)
            except Exception:
                logger.exception("drive_run crashed run=%s", run_id)
    finally:
        _workflow_tasks.pop(workflow_id, None)


def _persist_event(run_id: str, seq: int, payload: dict) -> None:
    try:
        with Session(engine) as session:
            session.add(
                RunEvent(
                    run_id=run_id,
                    seq=seq,
                    event_type=str(payload.get("event", "unknown")),
                    node_id=payload.get("node_id"),
                    ts=_utcnow(),
                    payload_json=json.dumps(payload, default=str, ensure_ascii=False),
                )
            )
            session.commit()
    except Exception:
        logger.exception("persist event failed run=%s seq=%s", run_id, seq)


async def _drive_run(run_id: str) -> None:
    from app.executor import run_workflow

    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None or run.status != "queued":
            return
        version = session.get(WorkflowVersion, run.workflow_version_id)
        if version is None:
            run.status = "failed"
            run.error = "version row missing"
            run.finished_at = _utcnow()
            session.add(run)
            session.commit()
            return
        try:
            workflow = load_workflow_schema(version)
        except Exception as exc:
            run.status = "failed"
            run.error = f"invalid workflow JSON: {exc}"
            run.finished_at = _utcnow()
            session.add(run)
            session.commit()
            return
        run.status = "running"
        run.started_at = _utcnow()
        session.add(run)
        session.commit()
        run_workflow_id = run.workflow_id

    abort_event = asyncio.Event()
    _abort_events[run_id] = abort_event
    seq_counter = {"n": 0}
    last_payload: dict = {}

    async def emit(payload: dict) -> None:
        seq = seq_counter["n"]
        seq_counter["n"] += 1
        enriched = {**payload, "run_id": run_id, "seq": seq}
        last_payload.clear()
        last_payload.update(enriched)
        _persist_event(run_id, seq, enriched)
        _fanout(run_id, enriched)

    terminal_error: Optional[str] = None
    try:
        with Session(engine) as exec_session:
            await run_workflow(
                workflow,
                emit,
                abort_event=abort_event,
                session=exec_session,
                workflow_id=run_workflow_id,
            )
    except Exception as exc:
        logger.exception("executor crashed run=%s", run_id)
        terminal_error = str(exc)
        await emit({
            "event": "run_failed",
            "node_id": None,
            "ts": _utcnow().isoformat(),
            "error": terminal_error,
        })

    terminal_event = last_payload.get("event")
    status_map = {
        "run_completed": "completed",
        "run_failed": "failed",
        "run_aborted": "aborted",
    }
    final_status = status_map.get(terminal_event or "", "completed")
    with Session(engine) as fin:
        row = fin.get(Run, run_id)
        if row is not None:
            row.status = final_status
            row.finished_at = _utcnow()
            if final_status == "failed":
                row.error = last_payload.get("error") or terminal_error
            fin.add(row)
            fin.commit()

    _abort_events.pop(run_id, None)


def request_abort(run_id: str) -> Run:
    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None:
            raise ValueError(f"run {run_id!r} not found")
        if run.status in ("completed", "failed", "aborted"):
            return run
        if run.status == "queued":
            for wf_id, q in list(_queues.items()):
                try:
                    q.remove(run_id)
                except ValueError:
                    continue
            run.status = "aborted"
            run.finished_at = _utcnow()
            session.add(run)
            payload = {
                "event": "run_aborted",
                "node_id": None,
                "ts": _utcnow().isoformat(),
                "run_id": run_id,
                "seq": 0,
            }
            session.add(
                RunEvent(
                    run_id=run_id,
                    seq=0,
                    event_type="run_aborted",
                    node_id=None,
                    ts=_utcnow(),
                    payload_json=json.dumps(payload, ensure_ascii=False),
                )
            )
            session.commit()
            session.refresh(run)
            _fanout(run_id, payload)
            return run
        ev = _abort_events.get(run_id)
        if ev is not None:
            ev.set()
        return run


def enqueue_run_standalone(
    workflow_id: str,
    *,
    source: str = "manual",
    trigger_id: Optional[str] = None,
    trigger_context: Optional[dict] = None,
) -> Run:
    """Convenience wrapper for callers without a Session (e.g. APScheduler
    jobs and the webhook endpoint). Opens its own session and commits."""
    with Session(engine) as session:
        return enqueue_run(
            workflow_id,
            session,
            source=source,
            trigger_id=trigger_id,
            trigger_context=trigger_context,
        )


__all__ = [
    "enqueue_run",
    "enqueue_run_standalone",
    "request_abort",
    "subscribe",
    "unsubscribe",
    "fetch_prior_events",
    "is_terminal",
]
