from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.db.models import Run, RunEvent, Workflow, WorkflowVersion
from app.db.session import get_session
from app.schemas_api import (
    RunCreate,
    RunEventOut,
    RunListItem,
    RunOut,
    RunReplayResponse,
    WorkflowVersionOut,
)
from app.services import runs as run_svc
from app.services import workflows as workflow_svc


router = APIRouter(tags=["runs"])


def _run_to_out(run: Run) -> RunOut:
    ctx: Optional[dict] = None
    if getattr(run, "trigger_context_json", None):
        try:
            parsed = json.loads(run.trigger_context_json)  # type: ignore[arg-type]
            if isinstance(parsed, dict):
                ctx = parsed
        except Exception:
            ctx = None
    return RunOut(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_version_id=run.workflow_version_id,
        status=run.status,  # type: ignore[arg-type]
        queued_at=run.queued_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error=run.error,
        source=getattr(run, "source", "manual") or "manual",
        trigger_id=getattr(run, "trigger_id", None),
        trigger_context=ctx,
    )


def _list_item(
    run: Run, workflow_name: str, version_index: int
) -> RunListItem:
    duration_ms: Optional[int] = None
    if run.started_at and run.finished_at:
        duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
    err_summary = run.error[:200] if run.error else None
    return RunListItem(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_name=workflow_name,
        workflow_version_id=run.workflow_version_id,
        version_index=version_index,
        status=run.status,  # type: ignore[arg-type]
        queued_at=run.queued_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_ms=duration_ms,
        error_summary=err_summary,
    )


@router.get("/api/runs", response_model=list[RunListItem])
def list_runs(
    workflow_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_session),
) -> list[RunListItem]:
    stmt = select(Run)
    if workflow_id:
        stmt = stmt.where(Run.workflow_id == workflow_id)
    stmt = stmt.order_by(Run.queued_at.desc()).offset(offset).limit(limit)  # type: ignore[attr-defined]
    runs = db.exec(stmt).all()

    items: list[RunListItem] = []
    for r in runs:
        wf = db.get(Workflow, r.workflow_id)
        wf_name = wf.name if wf else "(deleted)"
        v = db.get(WorkflowVersion, r.workflow_version_id)
        v_index = v.version_index if v else 0
        items.append(_list_item(r, wf_name, v_index))
    return items


@router.post("/api/runs", response_model=RunOut)
def create_run(
    body: dict = Body(...),
    db: Session = Depends(get_session),
) -> RunOut:
    workflow_id = body.get("workflow_id")
    if not workflow_id:
        raise HTTPException(400, detail="workflow_id required")
    version_id = body.get("version_id")
    try:
        run = run_svc.enqueue_run(workflow_id, db, version_id=version_id)
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc))
    return _run_to_out(run)


@router.post(
    "/api/workflows/{workflow_id}/runs", response_model=RunOut
)
def create_run_for_workflow(
    workflow_id: str,
    body: Optional[RunCreate] = None,
    db: Session = Depends(get_session),
) -> RunOut:
    try:
        run = run_svc.enqueue_run(workflow_id, db)
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc))
    return _run_to_out(run)


@router.get(
    "/api/runs/{run_id}", response_model=RunReplayResponse
)
def get_run(
    run_id: str, db: Session = Depends(get_session)
) -> RunReplayResponse:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, detail="run not found")
    version = db.get(WorkflowVersion, run.workflow_version_id)
    if version is None:
        raise HTTPException(404, detail="workflow version not found for run")
    events = db.exec(
        select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
    ).all()
    event_models = [
        RunEventOut(
            id=e.id or 0,
            run_id=e.run_id,
            seq=e.seq,
            event_type=e.event_type,
            node_id=e.node_id,
            ts=e.ts,
            payload=json.loads(e.payload_json),
        )
        for e in events
    ]
    authored = version.authored_by if version.authored_by in ("planner", "editor", "manual") else "manual"
    version_out = WorkflowVersionOut(
        id=version.id,
        workflow_id=version.workflow_id,
        version_index=version.version_index,
        authored_by=authored,  # type: ignore[arg-type]
        workflow=workflow_svc.workflow_json_of(version),  # type: ignore[arg-type]
        created_at=version.created_at,
    )
    return RunReplayResponse(
        run=_run_to_out(run),
        workflow_version=version_out,
        events=event_models,
    )


@router.get(
    "/api/runs/{run_id}/replay", response_model=RunReplayResponse
)
def get_run_replay(
    run_id: str, db: Session = Depends(get_session)
) -> RunReplayResponse:
    return get_run(run_id, db)


@router.post(
    "/api/runs/{run_id}/abort", response_model=RunOut
)
def abort_run(run_id: str, db: Session = Depends(get_session)) -> RunOut:
    try:
        run = run_svc.request_abort(run_id)
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc))
    refreshed = db.get(Run, run_id) or run
    return _run_to_out(refreshed)


__all__ = ["router"]
