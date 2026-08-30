"""Idempotent terminal path for autonomous runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlmodel import Session

from app.agents.autonomous import EventEmitter
from app.db.models import Run
from app.db.session import engine
from app.schemas_tasks import TaskResult
from app.services.agent_loop_metrics import AgentLoopMetrics, persist_metrics


_STATUS_TO_EVENT = {
    "completed": "run_completed",
    "failed": "run_failed",
    "aborted": "run_aborted",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_terminal(
    result: TaskResult | None,
    terminal_error: str | None,
) -> tuple[str, str]:
    if result is not None and result.success:
        return "completed", result.reason or "completed"
    if result is not None and result.reason == "aborted":
        return "aborted", result.reason
    if result is not None:
        return "failed", result.reason or "failed"
    if terminal_error:
        return "failed", "error"
    return "completed", "completed"


async def finalize_autonomous_run(
    run_id: str,
    result: TaskResult | None,
    *,
    terminal_error: str | None,
    emit: EventEmitter,
    metrics: AgentLoopMetrics | None,
) -> str:
    from app.tools.browser import end_run, stop_run_trace

    status, stop_reason = _resolve_terminal(result, terminal_error)
    event_name = _STATUS_TO_EVENT[status]
    user_err = None
    if result is not None:
        user_err = result.user_message or result.summary
    metrics_summary: dict | None = None

    with Session(engine) as session:
        row = session.get(Run, run_id)
        if row is not None and row.finished_at is not None:
            return _STATUS_TO_EVENT.get(row.status, "run_completed")

        if row is not None:
            row.status = status
            row.finished_at = _utcnow()
            if result is not None:
                row.result_json = json.dumps(
                    result.model_dump(), ensure_ascii=False, default=str
                )
                if result.reason:
                    stop_reason = result.reason
            if status == "failed":
                row.error = user_err or terminal_error
            if metrics is not None:
                metrics_summary = metrics.finalize(stop_reason, row)
                row.agent_loop_metrics_json = json.dumps(
                    metrics_summary, ensure_ascii=False, default=str
                )
            session.add(row)
            session.commit()

    if metrics is not None:
        if metrics_summary is None:
            metrics_summary = metrics.finalize(stop_reason)
        await emit({
            "event": "agent_loop_metrics",
            "node_id": None,
            "ts": _utcnow().isoformat(),
            **metrics_summary,
        })
        persist_metrics(run_id, metrics_summary)

    payload: dict = {
        "event": event_name,
        "node_id": None,
        "ts": _utcnow().isoformat(),
    }
    if result is not None:
        payload["output"] = result.model_dump()
    if status == "failed" and (user_err or terminal_error):
        payload["error"] = user_err or terminal_error
    await emit(payload)

    await stop_run_trace(run_id)
    await end_run(run_id=run_id)
    return event_name


__all__ = ["finalize_autonomous_run"]
