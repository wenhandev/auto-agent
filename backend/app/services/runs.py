from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import Session, select

from app.db.models import Run, RunEvent, Workflow, WorkflowVersion
from app.db.session import engine
from app.services import run_inputs as run_input_svc
from app.services import workflow_parameters as param_svc
from app.services.workflows import load_workflow_schema
from app.settings import settings


logger = logging.getLogger(__name__)


class QueueFullError(Exception):
    """Raised when the global run queue exceeds ``MAX_QUEUE_DEPTH``."""


# Per-workflow FIFO queues (run ids waiting for admission).
_workflow_queues: dict[str, deque[str]] = {}
# Round-robin order of workflows that have pending runs.
_rr_workflows: deque[str] = deque()
# Global enqueue order for queue-position reporting.
_global_queue_order: deque[str] = deque()
_run_workflow: dict[str, str] = {}

# Runs currently holding a dispatch slot (actively executing, not approval-paused).
_running: set[str] = set()
_running_by_workflow: dict[str, set[str]] = {}
# Runs paused on approval (context parked, slot released).
_approval_paused: set[str] = set()

_dispatcher_lock = asyncio.Lock()
_slot_waiters: dict[str, asyncio.Event] = {}

_abort_events: dict[str, asyncio.Event] = {}
_worker_last_seq: dict[str, int] = {}
_subscribers: dict[str, list[asyncio.Queue]] = {}
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def _schedule(coro_factory) -> None:
    """Schedule a coroutine without creating it when no loop is available."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro_factory())
        return
    except RuntimeError:
        pass
    if _main_loop is not None:
        asyncio.run_coroutine_threadsafe(coro_factory(), _main_loop)
    else:
        logger.debug("coroutine skipped (no event loop registered)")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _wakeup_dispatcher() -> None:
    _schedule(_ensure_dispatcher)


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
    return payload.get("event") in (
        "run_completed",
        "run_completed_with_errors",
        "run_failed",
        "run_aborted",
        "run_rejected",
    )


def _queued_run_count() -> int:
    return sum(len(q) for q in _workflow_queues.values())


def _can_admit_workflow(workflow_id: str) -> bool:
    q = _workflow_queues.get(workflow_id)
    if not q:
        return False
    if settings.allow_parallel_per_workflow:
        return True
    if _running_by_workflow.get(workflow_id):
        return False
    for rid in _approval_paused:
        if _run_workflow.get(rid) == workflow_id:
            return False
    return True


def _pick_next_admit() -> Optional[tuple[str, str]]:
    """Return (workflow_id, run_id) for the next run to admit, or None."""
    if not _rr_workflows:
        return None
    n = len(_rr_workflows)
    for _ in range(n):
        wf_id = _rr_workflows[0]
        _rr_workflows.rotate(-1)
        if not _can_admit_workflow(wf_id):
            continue
        q = _workflow_queues.get(wf_id)
        if not q:
            continue
        run_id = q[0]
        with Session(engine) as session:
            run_row = session.get(Run, run_id)
            if run_row is not None and getattr(run_row, "execution_mode", "cloud") == "worker":
                continue
        return wf_id, run_id
    return None


def _is_waiting(run_id: str) -> bool:
    if run_id in _running or run_id in _approval_paused:
        return False
    wf_id = _run_workflow.get(run_id)
    if wf_id is None:
        return False
    q = _workflow_queues.get(wf_id)
    return q is not None and run_id in q


def queue_position(run_id: str) -> Optional[int]:
    """1-based position among runs waiting for a dispatch slot."""
    if run_id in _running or run_id in _approval_paused:
        return None
    if not _is_waiting(run_id):
        return None
    ahead = 0
    for rid in _global_queue_order:
        if rid == run_id:
            return ahead + 1
        if _is_waiting(rid):
            ahead += 1
    return None


def queue_reason(run_id: str) -> Optional[str]:
    """Explain why a queued worker-mode run is still waiting."""
    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None or run.status != "queued":
            return None
        if getattr(run, "execution_mode", "cloud") != "worker":
            return None
        org_id = run.org_id
        worker_pool = run.worker_pool or "default"
        pinned = run.worker_id
        needs_headed = bool(run.record_video) or not settings.browser_headless

    from app.services import worker_hub

    if worker_hub.count_online_workers(org_id) == 0:
        return "waiting_for_worker"
    if not worker_hub.has_assignable_worker(
        org_id,
        worker_pool=worker_pool,
        pinned_worker_id=pinned,
        run_needs_headed=needs_headed,
    ):
        return "waiting_for_ready_worker"
    return None


def dispatcher_stats() -> dict[str, Any]:
    from app.services import browser_pool

    return {
        "running": len(_running),
        "queued": _queued_run_count(),
        "approval_paused": len(_approval_paused),
        "max_concurrent": settings.max_concurrent_browser_runs,
        "max_queue_depth": settings.max_queue_depth,
        "browser_pool": browser_pool.stats(),
    }


def _remove_run_from_queues(run_id: str) -> None:
    wf_id = _run_workflow.pop(run_id, None)
    if wf_id is not None:
        q = _workflow_queues.get(wf_id)
        if q is not None:
            try:
                q.remove(run_id)
            except ValueError:
                pass
            if not q:
                _workflow_queues.pop(wf_id, None)
                try:
                    _rr_workflows.remove(wf_id)
                except ValueError:
                    pass
    try:
        _global_queue_order.remove(run_id)
    except ValueError:
        pass


def remove_from_queue_for_tests(run_id: str) -> None:
    """Test helper: dequeue a run without starting it."""
    _remove_run_from_queues(run_id)


def _release_slot(run_id: str) -> None:
    wf_id = _run_workflow.get(run_id)
    _running.discard(run_id)
    if wf_id is not None:
        active = _running_by_workflow.get(wf_id)
        if active is not None:
            active.discard(run_id)
            if not active:
                _running_by_workflow.pop(wf_id, None)
    _wakeup_dispatcher()
    for ev in _slot_waiters.values():
        ev.set()


async def _reacquire_slot(run_id: str) -> None:
    """Wait for a global dispatch slot (used when resuming from approval)."""
    while len(_running) >= settings.max_concurrent_browser_runs:
        ev = _slot_waiters.setdefault(run_id, asyncio.Event())
        ev.clear()
        await ev.wait()
    _running.add(run_id)
    wf_id = _run_workflow.get(run_id)
    if wf_id:
        _running_by_workflow.setdefault(wf_id, set()).add(run_id)


async def on_approval_pause(run_id: str) -> None:
    """Release dispatch slot and park browser context while awaiting approval."""
    from app.tools.browser import park_for_approval

    parked = await park_for_approval(run_id=run_id)
    if not parked:
        logger.warning("approval pause: park cap reached run=%s", run_id)
    if run_id in _running:
        _approval_paused.add(run_id)
        _release_slot(run_id)
        _emit_pool_metric(run_id, "dispatch_slot_released")


async def on_approval_resume(run_id: str) -> None:
    """Re-acquire dispatch slot and unpark browser context after approval."""
    from app.tools.browser import unpark_after_approval

    if run_id in _approval_paused:
        await _reacquire_slot(run_id)
        _approval_paused.discard(run_id)
        _emit_pool_metric(run_id, "dispatch_slot_reacquired")
    await unpark_after_approval(run_id=run_id)


def _emit_pool_metric(run_id: str, kind: str) -> None:
    from app.services import browser_pool

    stats = browser_pool.stats()
    payload = {
        "event": "dispatcher_pool_metric",
        "run_id": run_id,
        "metric": kind,
        "running": len(_running),
        "queued": _queued_run_count(),
        "browser_pool": stats,
    }
    if stats.get("saturated"):
        payload["saturated"] = True
    logger.debug("dispatcher metric: %s", payload)


async def _ensure_dispatcher() -> None:
    async with _dispatcher_lock:
        while len(_running) < settings.max_concurrent_browser_runs:
            picked = _pick_next_admit()
            if picked is None:
                break
            wf_id, run_id = picked
            _workflow_queues[wf_id].popleft()
            _running.add(run_id)
            _running_by_workflow.setdefault(wf_id, set()).add(run_id)
            asyncio.create_task(_drive_run_wrapper(run_id))
        for ev in list(_slot_waiters.values()):
            ev.set()
    from app.services import worker_hub

    await worker_hub.dispatch_queued_worker_runs()


async def _drive_run_wrapper(run_id: str) -> None:
    try:
        await _drive_run(run_id)
    except Exception:
        logger.exception("drive_run crashed run=%s", run_id)
    finally:
        _running.discard(run_id)
        wf_id = _run_workflow.pop(run_id, None)
        if wf_id is not None:
            active = _running_by_workflow.get(wf_id)
            if active is not None:
                active.discard(run_id)
                if not active:
                    _running_by_workflow.pop(wf_id, None)
        _approval_paused.discard(run_id)
        _slot_waiters.pop(run_id, None)
        try:
            _global_queue_order.remove(run_id)
        except ValueError:
            pass
        _wakeup_dispatcher()


def enqueue_run(
    workflow_id: str,
    session: Session,
    *,
    version_id: Optional[str] = None,
    source: str = "manual",
    trigger_id: Optional[str] = None,
    trigger_context: Optional[dict] = None,
    browser_profile_id: Optional[str] = None,
    browser_session_id: Optional[str] = None,
    parameters: Optional[dict[str, Any]] = None,
    totp_identifier: Optional[str] = None,
    record_video: Optional[bool] = None,
    execution_mode: str = "cloud",
    worker_id: Optional[str] = None,
    worker_pool: Optional[str] = None,
) -> Run:
    if _queued_run_count() >= settings.max_queue_depth:
        raise QueueFullError(
            f"run queue full (max {settings.max_queue_depth})"
        )

    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise ValueError(f"workflow {workflow_id!r} not found")
    vid = version_id or workflow.current_version_id
    if vid is None:
        raise ValueError(f"workflow {workflow_id!r} has no version")
    version = session.get(WorkflowVersion, vid)
    if version is None:
        raise ValueError(f"workflow version {vid!r} not found")

    try:
        schema = load_workflow_schema(version)
        resolved_params = param_svc.validate_and_resolve_parameters(
            schema.parameters, parameters
        )
    except param_svc.ParameterValidationError:
        raise

    ctx_json: Optional[str] = None
    if trigger_context is not None:
        try:
            ctx_json = json.dumps(trigger_context, ensure_ascii=False, default=str)
        except Exception:
            logger.exception("failed to serialize trigger_context for workflow=%s", workflow_id)
            ctx_json = None

    if browser_profile_id is not None:
        from app.db.models import BrowserProfile

        profile = session.get(BrowserProfile, browser_profile_id)
        if profile is None:
            raise ValueError(f"browser profile {browser_profile_id!r} not found")

    if browser_session_id is not None and execution_mode != "worker":
        from app.db.models import BrowserSession
        from app.services import browser_sessions as session_svc

        bs = session.get(BrowserSession, browser_session_id)
        if bs is None:
            raise ValueError(f"browser session {browser_session_id!r} not found")
        if bs.status != "live":
            raise ValueError(f"browser session {browser_session_id!r} is {bs.status}")
        if not session_svc.is_active_in_process(browser_session_id):
            raise ValueError(
                f"browser session {browser_session_id!r} is not active in this process"
            )
        browser_provider_id = getattr(bs, "provider_id", None) or "local_playwright"
        browser_provider_metadata_json = getattr(bs, "provider_metadata_json", None)
    else:
        browser_provider_id = "local_playwright"
        browser_provider_metadata_json = None

    params_json: Optional[str] = None
    run_id = str(uuid.uuid4())
    if resolved_params and schema.parameters:
        try:
            resolved_params = run_input_svc.materialize_file_parameters(
                workflow_id,
                run_id,
                resolved_params,
                schema.parameters,
            )
        except run_input_svc.RunInputError as exc:
            raise param_svc.ParameterValidationError(str(exc)) from exc
    if resolved_params:
        params_json = json.dumps(resolved_params, ensure_ascii=False, default=str)

    run = Run(
        id=run_id,
        workflow_id=workflow_id,
        workflow_version_id=vid,
        org_id=workflow.org_id,
        status="queued",
        queued_at=_utcnow(),
        source=source,
        trigger_id=trigger_id,
        trigger_context_json=ctx_json,
        parameters_json=params_json,
        browser_profile_id=browser_profile_id,
        browser_session_id=browser_session_id,
        browser_provider_id=browser_provider_id,
        browser_provider_metadata_json=browser_provider_metadata_json,
        totp_identifier=totp_identifier,
        record_video=record_video,
        execution_mode=execution_mode,
        worker_id=worker_id,
        worker_pool=worker_pool or ("default" if execution_mode == "worker" else None),
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    _workflow_queues.setdefault(workflow_id, deque()).append(run.id)
    if workflow_id not in _rr_workflows:
        _rr_workflows.append(workflow_id)
    _global_queue_order.append(run.id)
    _run_workflow[run.id] = workflow_id

    from app.services import browser_pool

    if browser_pool.stats().get("saturated"):
        _emit_pool_metric(run.id, "pool_saturated_on_enqueue")

    _wakeup_dispatcher()
    return run


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
        return
    try:
        from app.services import cost_tracking as cost_svc

        cost_svc.on_run_event(run_id, payload)
    except Exception:
        logger.exception("cost aggregation failed run=%s seq=%s", run_id, seq)


def _trigger_namespace_from_run(run: Run) -> Optional[dict[str, Any]]:
    if not run.trigger_context_json:
        return None
    try:
        ctx = json.loads(run.trigger_context_json)
    except Exception:
        return None
    if not isinstance(ctx, dict):
        return None
    payload = ctx.get("context")
    if payload is None:
        payload = ctx.get("body") or {}
    return {
        "context": payload if isinstance(payload, dict) else {"_value": payload},
        "input": ctx.get("body") if isinstance(ctx.get("body"), dict) else payload,
        "body": ctx.get("body"),
        "kind": ctx.get("kind") or run.source,
        "id": ctx.get("trigger_id") or run.trigger_id,
        "headers": ctx.get("headers") or {},
    }


async def _drive_run(run_id: str) -> None:
    from app.services import runtime_engine as runtime_engine_svc

    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None or run.status != "queued":
            return
        if getattr(run, "execution_mode", "cloud") == "worker":
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
        trigger_namespace = _trigger_namespace_from_run(run)
        browser_profile_id = run.browser_profile_id
        browser_session_id = run.browser_session_id
        totp_identifier = run.totp_identifier
        record_video = run.record_video
        params_namespace = param_svc.load_resolved_parameters_json(
            run.parameters_json
        )

    abort_event = asyncio.Event()
    _abort_events[run_id] = abort_event

    def persist_event(rid: str, seq: int, enriched: dict) -> None:
        _persist_event(rid, seq, enriched)
        _fanout(rid, enriched)

    async def emit(_enriched: dict) -> None:
        return None

    await runtime_engine_svc.execute_run(
        run_id=run_id,
        workflow=workflow,
        emit=emit,
        abort_event=abort_event,
        browser_profile_id=browser_profile_id,
        browser_session_id=browser_session_id,
        trigger_namespace=trigger_namespace,
        params_namespace=params_namespace,
        totp_identifier=totp_identifier,
        record_video=record_video,
        workflow_id=run_workflow_id,
        persist_event=persist_event,
    )
    _abort_events.pop(run_id, None)


def request_abort(run_id: str) -> Run:
    from app.services import approvals as approvals_svc

    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None:
            raise ValueError(f"run {run_id!r} not found")
        if run.status in (
            "completed",
            "completed_with_errors",
            "failed",
            "aborted",
            "rejected",
        ):
            return run
        if run.status == "queued":
            _remove_run_from_queues(run_id)
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
            from app.services import webhooks as webhook_svc

            try:
                webhook_svc.enqueue_run_terminal(
                    run_id,
                    "run_aborted",
                    status="aborted",
                    extra=payload,
                )
            except Exception:
                logger.exception("webhook enqueue failed run=%s event=run_aborted", run_id)
            return run
        if getattr(run, "execution_mode", "cloud") == "worker" and run.status == "running":
            from app.services import worker_hub

            _schedule(lambda: worker_hub.request_abort_on_worker(run_id))
            return run
        approvals_svc.mark_pending_lost_for_run(session, run_id)
        ev = _abort_events.get(run_id)
        if ev is not None:
            ev.set()
        return run


def fail_in_flight_runs_on_startup() -> int:
    """Mark runs that were queued/running before restart as failed."""
    now = _utcnow()
    count = 0
    with Session(engine) as session:
        rows = session.exec(
            select(Run).where(Run.status.in_(("queued", "running")))  # type: ignore[attr-defined]
        ).all()
        for run in rows:
            run.status = "failed"
            run.error = "backend restarted; run cannot resume"
            run.finished_at = now
            session.add(run)
            count += 1
        if count:
            session.commit()
    return count


def reset_dispatcher_for_tests() -> None:
    """Clear in-memory dispatcher state (tests only)."""
    _workflow_queues.clear()
    _rr_workflows.clear()
    _global_queue_order.clear()
    _run_workflow.clear()
    _running.clear()
    _running_by_workflow.clear()
    _approval_paused.clear()
    _slot_waiters.clear()
    _abort_events.clear()
    _worker_last_seq.clear()


def enqueue_run_standalone(
    workflow_id: str,
    *,
    source: str = "manual",
    trigger_id: Optional[str] = None,
    trigger_context: Optional[dict] = None,
    browser_profile_id: Optional[str] = None,
    parameters: Optional[dict[str, Any]] = None,
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
            browser_profile_id=browser_profile_id,
            parameters=parameters,
        )


create_queued_run = enqueue_run_standalone


def persist_and_fanout(run_id: str, seq: int, payload: dict) -> None:
    """Persist a run event and fan out to live subscribers."""
    _persist_event(run_id, seq, payload)
    _fanout(run_id, payload)


def register_abort_event(run_id: str) -> asyncio.Event:
    ev = asyncio.Event()
    _abort_events[run_id] = ev
    return ev


def clear_abort_event(run_id: str) -> None:
    _abort_events.pop(run_id, None)


def wakeup_dispatcher() -> None:
    _wakeup_dispatcher()


def remove_from_dispatcher_queue(run_id: str) -> None:
    _remove_run_from_queues(run_id)


def list_queued_worker_run_ids() -> list[str]:
    if not _global_queue_order:
        return []
    ordered = list(_global_queue_order)
    out: list[str] = []
    with Session(engine) as session:
        for run_id in ordered:
            run = session.get(Run, run_id)
            if run is None or run.status != "queued":
                continue
            if getattr(run, "execution_mode", "cloud") == "worker":
                out.append(run_id)
    return out


async def ingest_worker_event(run_id: str, seq: int, payload: dict) -> None:
    last = _worker_last_seq.get(run_id, -1)
    if seq <= last:
        logger.warning("reject stale worker event run=%s seq=%s last=%s", run_id, seq, last)
        return
    _worker_last_seq[run_id] = seq
    enriched = {**payload, "run_id": run_id, "seq": seq}
    _persist_event(run_id, seq, enriched)
    _fanout(run_id, enriched)
    if not is_terminal(enriched):
        return
    terminal_event = enriched.get("event") or ""
    status_map = {
        "run_completed": "completed",
        "run_completed_with_errors": "completed_with_errors",
        "run_failed": "failed",
        "run_aborted": "aborted",
        "run_rejected": "rejected",
    }
    final_status = status_map.get(str(terminal_event), "completed")
    with Session(engine) as session:
        row = session.get(Run, run_id)
        if row is not None:
            row.status = final_status
            row.finished_at = _utcnow()
            if final_status == "failed":
                row.error = enriched.get("error")
            session.add(row)
            session.commit()
    from app.services import livestream as livestream_svc
    from app.services import webhooks as webhook_svc

    try:
        webhook_svc.enqueue_run_terminal(
            run_id,
            str(terminal_event),
            status=final_status,
            extra=enriched,
        )
    except Exception:
        logger.exception("webhook enqueue failed run=%s event=%s", run_id, terminal_event)
    await livestream_svc.on_run_ended(run_id)
    _worker_last_seq.pop(run_id, None)


__all__ = [
    "QueueFullError",
    "create_queued_run",
    "dispatcher_stats",
    "enqueue_run",
    "enqueue_run_standalone",
    "fail_in_flight_runs_on_startup",
    "on_approval_pause",
    "on_approval_resume",
    "queue_position",
    "queue_reason",
    "remove_from_queue_for_tests",
    "request_abort",
    "reset_dispatcher_for_tests",
    "subscribe",
    "unsubscribe",
    "fetch_prior_events",
    "is_terminal",
    "persist_and_fanout",
    "register_abort_event",
    "clear_abort_event",
    "wakeup_dispatcher",
    "remove_from_dispatcher_queue",
    "list_queued_worker_run_ids",
    "ingest_worker_event",
]
