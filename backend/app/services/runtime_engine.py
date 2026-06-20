"""Shared workflow execution engine for cloud and worker runtimes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

from sqlmodel import Session

from app.db.models import Run, WorkflowVersion
from app.db.session import engine
from app.executor import run_workflow
from app.schemas import Workflow
from app.services import artifact_context
from app.services import artifacts as artifact_svc
from app.services import session_recording as session_rec_svc
from app.services import workflow_parameters as param_svc
from app.services import workflows as workflow_svc
from app.tools.browser import begin_run, end_run, start_run_trace, stop_run_trace


logger = logging.getLogger(__name__)

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]
PersistFn = Callable[[str, int, dict[str, Any]], None]
FinalizeFn = Callable[[str, str, dict[str, Any], Optional[str]], Awaitable[None]]


async def execute_run(
    *,
    run_id: str,
    workflow: Workflow,
    emit: EmitFn,
    abort_event: asyncio.Event,
    browser_profile_id: Optional[str] = None,
    browser_session_id: Optional[str] = None,
    trigger_namespace: Optional[dict[str, Any]] = None,
    params_namespace: Optional[dict[str, Any]] = None,
    totp_identifier: Optional[str] = None,
    record_video: Optional[bool] = None,
    workflow_id: Optional[str] = None,
    persist_event: Optional[PersistFn] = None,
    finalize_run: Optional[FinalizeFn] = None,
    llm_client_factory: Optional[Any] = None,
) -> dict[str, Any]:
    """Run workflow to completion; return last terminal payload.

    Injectable hooks for worker runtime:
    - ``emit``: deliver enriched run events (worker uploads via WebSocket)
    - ``abort_event``: cooperative cancellation
    - ``llm_client_factory``: optional override installed via ``set_llm_client_factory``
    """
    if llm_client_factory is not None:
        from app.agents.model import set_llm_client_factory

        set_llm_client_factory(llm_client_factory)
    seq_counter = {"n": 0}
    last_payload: dict[str, Any] = {}

    async def emit_wrapped(payload: dict[str, Any]) -> None:
        seq = seq_counter["n"]
        seq_counter["n"] += 1
        artifact_context.set_run_context(
            run_id,
            node_id=payload.get("node_id"),
            step_index=payload.get("step_index"),
        )
        enriched_payload = await artifact_svc.enrich_event_payload(run_id, payload)
        enriched = {**enriched_payload, "run_id": run_id, "seq": seq}
        last_payload.clear()
        last_payload.update(enriched)
        if persist_event is not None:
            persist_event(run_id, seq, enriched)
        await emit(enriched)

    artifact_context.set_run_context(run_id)
    await begin_run(
        browser_profile_id,
        run_id=run_id,
        browser_session_id=browser_session_id,
    )
    if session_rec_svc.is_enabled(record_video):
        await session_rec_svc.start_recording(run_id)
    await start_run_trace(run_id)

    terminal_error: Optional[str] = None
    try:
        with Session(engine) as exec_session:
            await run_workflow(
                workflow,
                emit_wrapped,
                abort_event=abort_event,
                session=exec_session,
                workflow_id=workflow_id,
                run_id=run_id,
                trigger_namespace=trigger_namespace,
                params_namespace=params_namespace,
                totp_identifier=totp_identifier,
            )
    except Exception as exc:
        logger.exception("executor crashed run=%s", run_id)
        terminal_error = str(exc)
        await emit_wrapped({
            "event": "run_failed",
            "node_id": None,
            "ts": _iso_now(),
            "error": terminal_error,
        })

    terminal_event = last_payload.get("event") or ""
    status_map = {
        "run_completed": "completed",
        "run_completed_with_errors": "completed_with_errors",
        "run_failed": "failed",
        "run_aborted": "aborted",
        "run_rejected": "rejected",
    }
    final_status = status_map.get(terminal_event, "completed")

    if finalize_run is not None:
        await finalize_run(run_id, final_status, last_payload, terminal_error)
    else:
        await _default_finalize(
            run_id,
            final_status,
            last_payload,
            terminal_error,
            browser_session_id=browser_session_id,
            record_video=record_video,
        )

    artifact_context.clear_run_context()
    if llm_client_factory is not None:
        from app.agents.model import clear_llm_client_factory

        clear_llm_client_factory()
    return last_payload


def _iso_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


async def _default_finalize(
    run_id: str,
    final_status: str,
    last_payload: dict[str, Any],
    terminal_error: Optional[str],
    *,
    browser_session_id: Optional[str],
    record_video: Optional[bool],
) -> None:
    from datetime import datetime, timezone

    from app.services import livestream as livestream_svc
    from app.services import webhooks as webhook_svc

    now = datetime.now(timezone.utc)
    with Session(engine) as fin:
        row = fin.get(Run, run_id)
        if row is not None:
            row.status = final_status
            row.finished_at = now
            if final_status == "failed":
                row.error = last_payload.get("error") or terminal_error
            fin.add(row)
            fin.commit()

    terminal_event = last_payload.get("event")
    if terminal_event:
        try:
            webhook_svc.enqueue_run_terminal(
                run_id,
                str(terminal_event),
                status=final_status,
                extra=last_payload,
            )
        except Exception:
            logger.exception("webhook enqueue failed run=%s event=%s", run_id, terminal_event)

    await livestream_svc.on_run_ended(run_id)
    await stop_run_trace(run_id)
    if session_rec_svc.is_enabled(record_video):
        await session_rec_svc.finalize_recording(run_id)
    await end_run(run_id=run_id, browser_session_id=browser_session_id)


def load_run_context(run_id: str) -> Optional[dict[str, Any]]:
    """Load workflow + namespaces for a queued run (promote to running separately)."""
    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None:
            return None
        version = session.get(WorkflowVersion, run.workflow_version_id)
        if version is None:
            return None
        try:
            workflow = workflow_svc.load_workflow_schema(version)
        except Exception:
            return None
        trigger_namespace = _trigger_namespace_from_run(run)
        params_namespace = param_svc.load_resolved_parameters_json(run.parameters_json)
        return {
            "run": run,
            "workflow": workflow,
            "trigger_namespace": trigger_namespace,
            "params_namespace": params_namespace,
            "browser_profile_id": run.browser_profile_id,
            "browser_session_id": run.browser_session_id,
            "totp_identifier": run.totp_identifier,
            "record_video": run.record_video,
            "workflow_id": run.workflow_id,
        }


def _trigger_namespace_from_run(run: Run) -> dict[str, Any]:
    import json

    ctx: dict[str, Any] = {}
    if run.trigger_context_json:
        try:
            parsed = json.loads(run.trigger_context_json)
            if isinstance(parsed, dict):
                ctx = parsed
        except Exception:
            ctx = {}
    return {
        "kind": ctx.get("kind") or run.source,
        "id": ctx.get("trigger_id") or run.trigger_id,
        "headers": ctx.get("headers") or {},
    }


__all__ = ["execute_run", "load_run_context"]
