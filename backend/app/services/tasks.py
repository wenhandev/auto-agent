"""Autonomous task run lifecycle: create, enqueue, drive."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import Session, select

from app.agents.autonomous import run_task as run_autonomous_task
from app.db.models import Run, Workflow
from app.db.session import engine
from app.schemas_tasks import TaskResult, TaskSpec
from app.services import runs as run_svc
from app.services.autonomous_workflows import AUTONOMOUS_WORKFLOW_NAME


logger = logging.getLogger(__name__)

_task_queue: deque[str] = deque()
_task_loop_task: Optional[asyncio.Task] = None
_task_loop_lock = asyncio.Lock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_autonomous_workflow(session: Session) -> tuple[str, str]:
    wf = session.exec(
        select(Workflow).where(Workflow.name == AUTONOMOUS_WORKFLOW_NAME)
    ).first()
    if wf is not None and wf.current_version_id:
        if wf.status != "archived":
            wf.status = "archived"
            session.add(wf)
            session.commit()
        return wf.id, wf.current_version_id

    from app.services import workflows as workflow_svc

    if wf is None:
        wf = workflow_svc.create_workflow(
            name=AUTONOMOUS_WORKFLOW_NAME,
            session=session,
            description="System placeholder for autonomous task runs (hidden)",
            authored_by="manual",
        )
        wf.status = "archived"
        session.add(wf)
        session.commit()
        session.refresh(wf)
    return wf.id, wf.current_version_id  # type: ignore[arg-type]


def create_task(
    session: Session,
    spec: TaskSpec,
    *,
    execution_mode: str | None = None,
) -> Run:
    from app.settings import settings

    mode = execution_mode or (
        "worker" if settings.execution_backend == "control_plane_only" else "cloud"
    )
    wf_id, version_id = _ensure_autonomous_workflow(session)
    allowed_tools_json = (
        json.dumps(spec.allowed_tools, ensure_ascii=False)
        if spec.allowed_tools is not None
        else None
    )
    allowed_domains_json = (
        json.dumps(spec.allowed_domains, ensure_ascii=False)
        if spec.allowed_domains is not None
        else None
    )
    data_schema_json = (
        json.dumps(spec.data_schema, ensure_ascii=False)
        if spec.data_schema is not None
        else None
    )

    run = Run(
        workflow_id=wf_id,
        workflow_version_id=version_id,
        status="queued",
        mode="autonomous",
        queued_at=_utcnow(),
        source="task",
        objective=spec.objective,
        start_url=spec.start_url,
        max_steps=spec.max_steps,
        max_seconds=spec.max_seconds,
        success_criteria=spec.success_criteria,
        allowed_domains_json=allowed_domains_json,
        data_schema_json=data_schema_json,
        require_confirmation=spec.require_confirmation,
        allowed_tools_json=allowed_tools_json,
        execution_mode=mode,
        worker_pool="default" if mode == "worker" else None,
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    if mode == "worker":
        run_svc.schedule_worker_run(run.id, wf_id)
    else:
        _task_queue.append(run.id)
        run_svc._schedule(_ensure_task_loop)
    return run


async def _ensure_task_loop() -> None:
    async with _task_loop_lock:
        global _task_loop_task
        if _task_loop_task is None or _task_loop_task.done():
            _task_loop_task = asyncio.create_task(_task_dequeue_loop())


async def _task_dequeue_loop() -> None:
    global _task_loop_task
    try:
        while _task_queue:
            run_id = _task_queue.popleft()
            with Session(engine) as session:
                run = session.get(Run, run_id)
                if run is not None and getattr(run, "execution_mode", "cloud") == "worker":
                    continue
            try:
                await _drive_autonomous_run(run_id)
            except Exception:
                logger.exception("autonomous drive crashed run=%s", run_id)
    finally:
        _task_loop_task = None


def _load_browser_session_memory(run: Run) -> list[dict[str, Any]]:
    if not run.browser_session_id:
        return []
    from app.services import browser_sessions as browser_session_svc

    try:
        with Session(engine) as session:
            return browser_session_svc.list_memory_entries(session, run.browser_session_id)
    except Exception:
        logger.exception("failed to load browser session memory run=%s", run.id)
        return []


def _run_to_task_spec(run: Run) -> TaskSpec:
    allowed_domains = None
    if run.allowed_domains_json:
        allowed_domains = json.loads(run.allowed_domains_json)
    data_schema = None
    if run.data_schema_json:
        data_schema = json.loads(run.data_schema_json)
    allowed_tools = None
    if run.allowed_tools_json:
        allowed_tools = json.loads(run.allowed_tools_json)

    return TaskSpec(
        objective=run.objective or "",
        start_url=run.start_url,
        max_steps=run.max_steps or 30,
        max_seconds=run.max_seconds or 300,
        success_criteria=run.success_criteria,
        allowed_domains=allowed_domains,
        data_schema=data_schema,
        require_confirmation=bool(run.require_confirmation),
        allowed_tools=allowed_tools,
        session_memory=_load_browser_session_memory(run),
    )


async def _drive_autonomous_run(run_id: str) -> None:
    from app.services import artifact_context
    from app.services import artifacts as artifact_svc
    from app.tools.browser import start_run_trace

    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None or run.status != "queued" or run.mode != "autonomous":
            return
        run.status = "running"
        run.started_at = _utcnow()
        session.add(run)
        session.commit()
        spec = _run_to_task_spec(run)

    abort_event = run_svc.register_abort_event(run_id)
    seq_counter = {"n": 0}

    from app.services.agent_loop_metrics import (
        AgentLoopMetrics,
        observe_event,
        reset_metrics,
        set_metrics,
    )

    loop_metrics = AgentLoopMetrics()
    metrics_token = set_metrics(loop_metrics)

    artifact_context.set_run_context(run_id)
    await start_run_trace(run_id)

    async def emit(payload: dict) -> None:
        observe_event(payload)
        seq = seq_counter["n"]
        seq_counter["n"] += 1
        artifact_context.set_run_context(
            run_id,
            node_id=payload.get("node_id"),
            step_index=payload.get("step_index"),
        )
        enriched_payload = await artifact_svc.enrich_event_payload(run_id, payload)
        enriched = {**enriched_payload, "run_id": run_id, "seq": seq}
        run_svc.persist_and_fanout(run_id, seq, enriched)

    terminal_error: Optional[str] = None
    task_result: Optional[TaskResult] = None
    try:
        task_result = await run_autonomous_task(
            spec,
            emit,
            abort_event=abort_event,
        )
    except Exception as exc:
        logger.exception("autonomous task crashed run=%s", run_id)
        terminal_error = str(exc)
        from app.agents.autonomous_errors import resolve_user_failure_message

        user_msg = await resolve_user_failure_message(
            objective=spec.objective,
            summary=terminal_error,
            reason="error",
            items=[],
        )
        task_result = TaskResult(
            success=False,
            summary=user_msg,
            user_message=user_msg,
            reason="error",
            steps_taken=0,
            items=[],
        )
        await emit({
            "event": "task_finished",
            "success": False,
            "result": task_result.model_dump(),
            "ts": _utcnow().isoformat(),
        })

    from app.services.turn_finalize import finalize_autonomous_run

    await finalize_autonomous_run(
        run_id,
        task_result,
        terminal_error=terminal_error,
        emit=emit,
        metrics=loop_metrics,
    )

    run_svc.clear_abort_event(run_id)
    artifact_context.clear_run_context()
    reset_metrics(metrics_token)


def get_task_result(run: Run) -> Optional[TaskResult]:
    if not run.result_json:
        return None
    try:
        data = json.loads(run.result_json)
        return TaskResult.model_validate(data)
    except Exception:
        return None


__all__ = ["create_task", "get_task_result", "_run_to_task_spec"]
