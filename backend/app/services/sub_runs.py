"""Sub-workflow invocation with parent/child run linkage."""
from __future__ import annotations

import contextvars
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import Session

from app.db.models import Run, RunEvent, Workflow as WorkflowRow, WorkflowVersion
from app.db.session import engine
from app.nodes.result import NodeResult
from app.schemas import Workflow as WorkflowSchema
from app.services.workflows import load_workflow_schema

logger = logging.getLogger(__name__)

MAX_SUBWORKFLOW_DEPTH = 5
_subworkflow_depth: contextvars.ContextVar[int] = contextvars.ContextVar(
    "subworkflow_depth", default=0
)


@dataclass
class SubworkflowResult:
    child_run_id: str
    status: str
    final_output: Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _persist_event(run_id: str, seq: int, payload: dict) -> None:
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
    try:
        from app.services import cost_tracking as cost_svc

        cost_svc.on_run_event(run_id, payload)
    except Exception:
        logger.exception("cost aggregation failed run=%s seq=%s", run_id, seq)


async def run_subworkflow(
    *,
    parent_run_id: str,
    workflow_id: str,
    version_id: Optional[str],
    input_data: dict[str, Any],
    session: Optional[Session] = None,
    emit: Any = None,
    abort_event: Any = None,
) -> SubworkflowResult:
    """Create a child run and execute the target workflow synchronously."""
    depth = _subworkflow_depth.get()
    if depth >= MAX_SUBWORKFLOW_DEPTH:
        raise RecursionError(
            f"subworkflow recursion depth exceeded ({MAX_SUBWORKFLOW_DEPTH})"
        )

    token = _subworkflow_depth.set(depth + 1)
    try:
        return await _run_subworkflow_inner(
            parent_run_id=parent_run_id,
            workflow_id=workflow_id,
            version_id=version_id,
            input_data=input_data,
            session=session,
            emit=emit,
            abort_event=abort_event,
        )
    finally:
        _subworkflow_depth.reset(token)


async def _run_subworkflow_inner(
    *,
    parent_run_id: str,
    workflow_id: str,
    version_id: Optional[str],
    input_data: dict[str, Any],
    session: Optional[Session] = None,
    emit: Any = None,
    abort_event: Any = None,
) -> SubworkflowResult:
    from app.executor import run_workflow

    own_session = session is None
    db = session or Session(engine)
    try:
        workflow_row = db.get(WorkflowRow, workflow_id)
        if workflow_row is None:
            raise ValueError(f"subworkflow target workflow {workflow_id!r} not found")
        vid = version_id or workflow_row.current_version_id
        if vid is None:
            raise ValueError(f"workflow {workflow_id!r} has no version")
        version = db.get(WorkflowVersion, vid)
        if version is None:
            raise ValueError(f"workflow version {vid!r} not found")

        child = Run(
            workflow_id=workflow_id,
            workflow_version_id=vid,
            status="running",
            queued_at=_utcnow(),
            started_at=_utcnow(),
            parent_run_id=parent_run_id,
        )
        db.add(child)
        db.commit()
        db.refresh(child)
        child_run_id = child.id

        wf_schema: WorkflowSchema = load_workflow_schema(version)
        seq_counter = {"n": 0}
        last_output: Any = None
        terminal_status = "completed"

        async def child_emit(payload: dict) -> None:
            nonlocal last_output, terminal_status
            seq = seq_counter["n"]
            seq_counter["n"] += 1
            enriched = {**payload, "run_id": child_run_id, "seq": seq}
            _persist_event(child_run_id, seq, enriched)
            if payload.get("event") == "node_completed" and payload.get("node_id"):
                last_output = payload.get("output")
            ev = payload.get("event")
            if ev == "run_failed":
                terminal_status = "failed"
            elif ev == "run_aborted":
                terminal_status = "aborted"
            elif ev == "run_completed_with_errors":
                terminal_status = "completed_with_errors"

        initial_context: dict[str, NodeResult] = {
            "_input": NodeResult.single(input_data),
        }

        await run_workflow(
            wf_schema,
            child_emit,
            abort_event=abort_event,
            session=db,
            workflow_id=workflow_id,
            run_id=child_run_id,
            initial_context=initial_context,
        )

        row = db.get(Run, child_run_id)
        if row is not None:
            row.status = terminal_status
            row.finished_at = _utcnow()
            db.add(row)
            db.commit()

        return SubworkflowResult(
            child_run_id=child_run_id,
            status=terminal_status,
            final_output=last_output,
        )
    finally:
        if own_session:
            db.close()


__all__ = [
    "MAX_SUBWORKFLOW_DEPTH",
    "SubworkflowResult",
    "run_subworkflow",
]
