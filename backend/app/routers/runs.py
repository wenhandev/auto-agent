from __future__ import annotations

import json
import mimetypes
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlmodel import Session, select

from app.auth.context import AuthContext, get_org_context, org_scope_filter, require_org_match

from app.db.models import Run, RunArtifact, RunEvent, Worker, Workflow, WorkflowVersion
from app.db.session import get_session
from app.schemas_api import (
    PendingApproval,
    RunArtifactOut,
    RunCostSummaryOut,
    RunCreate,
    RunEventOut,
    RunListItem,
    RunOut,
    RunReplayResponse,
    TaskResultOut,
    UsageSummaryOut,
    NodeCostEntry,
    WorkflowVersionOut,
)
from app.services import approvals as approvals_svc
from app.services.autonomous_workflows import run_list_label
from app.services import artifacts as artifact_svc
from app.services import cost_tracking as cost_svc
from app.services import run_inputs as run_input_svc
from app.services import runs as run_svc
from app.services import workflow_parameters as param_svc
from app.services import workflows as workflow_svc


router = APIRouter(tags=["runs"])


def _parse_json_dict(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _run_parameters_out(run: Run, db: Optional[Session] = None) -> Optional[dict]:
    if not getattr(run, "parameters_json", None):
        return None
    try:
        parsed = json.loads(run.parameters_json)  # type: ignore[arg-type]
    except Exception:
        return None
    if not isinstance(parsed, dict) or not parsed:
        return None
    if db is None:
        return parsed
    version = db.get(WorkflowVersion, run.workflow_version_id)
    if version is None:
        return parsed
    try:
        schema = workflow_svc.load_workflow_schema(version)
    except Exception:
        return parsed
    return param_svc.mask_parameters(parsed, schema.parameters)


def _pending_approval_out(row) -> PendingApproval:
    return PendingApproval(
        node_id=row.node_id,
        prompt=row.prompt,
        inputs_schema=list(row.inputs_schema or []),
        requested_at=row.requested_at,
    )


def _run_cost_fields(run: Run) -> dict:
    summary_raw = cost_svc.parse_usage_summary(getattr(run, "usage_summary_json", None))
    usage_summary = UsageSummaryOut.model_validate(summary_raw) if summary_raw else None
    node_cost_rows = cost_svc.parse_node_costs(getattr(run, "node_cost_json", None))
    node_costs = [NodeCostEntry.model_validate(row) for row in node_cost_rows]
    return {
        "total_input_tokens": int(getattr(run, "total_input_tokens", 0) or 0),
        "total_output_tokens": int(getattr(run, "total_output_tokens", 0) or 0),
        "total_llm_calls": int(getattr(run, "total_llm_calls", 0) or 0),
        "total_vision_calls": int(getattr(run, "total_vision_calls", 0) or 0),
        "estimated_cost_usd": getattr(run, "estimated_cost_usd", None),
        "cost_note": getattr(run, "cost_note", None),
        "usage_summary": usage_summary,
        "node_costs": node_costs,
    }


def _worker_name(db: Optional[Session], worker_id: Optional[str]) -> Optional[str]:
    if db is None or not worker_id:
        return None
    worker = db.get(Worker, worker_id)
    if worker is None:
        return None
    return worker.display_name or worker.hostname


def _run_to_out(
    run: Run,
    db: Optional[Session] = None,
    pending: Optional[PendingApproval] = None,
) -> RunOut:
    ctx: Optional[dict] = None
    if getattr(run, "trigger_context_json", None):
        try:
            parsed = json.loads(run.trigger_context_json)  # type: ignore[arg-type]
            if isinstance(parsed, dict):
                ctx = parsed
        except Exception:
            ctx = None
    counts: dict[str, int] = {}
    if db is not None:
        counts = artifact_svc.count_by_kind(run.id, session=db)
        if pending is None:
            pending_row = approvals_svc.pending_for_run(db, run.id)
            if pending_row is not None:
                pending = _pending_approval_out(pending_row)
    return RunOut(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_version_id=run.workflow_version_id,
        status=run.status,  # type: ignore[arg-type]
        mode=getattr(run, "mode", "graph") or "graph",  # type: ignore[arg-type]
        queued_at=run.queued_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error=run.error,
        source=getattr(run, "source", "manual") or "manual",
        trigger_id=getattr(run, "trigger_id", None),
        trigger_context=ctx,
        parameters=_run_parameters_out(run, db),
        artifact_counts=counts,
        browser_profile_id=getattr(run, "browser_profile_id", None),
        browser_session_id=getattr(run, "browser_session_id", None),
        browser_provider_id=getattr(run, "browser_provider_id", None),
        browser_provider_metadata=_parse_json_dict(
            getattr(run, "browser_provider_metadata_json", None)
        ),
        agent_loop_metrics=_parse_json_dict(getattr(run, "agent_loop_metrics_json", None))
        or None,
        totp_identifier=getattr(run, "totp_identifier", None),
        pending_approval=pending,
        queue_position=run_svc.queue_position(run.id),
        execution_mode=getattr(run, "execution_mode", "cloud") or "cloud",  # type: ignore[arg-type]
        worker_id=getattr(run, "worker_id", None),
        worker_pool=getattr(run, "worker_pool", None),
        worker_name=_worker_name(db, getattr(run, "worker_id", None)),
        queue_reason=run_svc.queue_reason(run.id),
        objective=getattr(run, "objective", None),
        task_result=_task_result_out(run),
        **_run_cost_fields(run),
    )


def _task_result_out(run: Run) -> Optional[TaskResultOut]:
    if getattr(run, "mode", "graph") != "autonomous":
        return None
    from app.services import tasks as task_svc

    result = task_svc.get_task_result(run)
    if result is None:
        return None
    return TaskResultOut.model_validate(result.model_dump())


def _artifact_to_out(row: RunArtifact) -> RunArtifactOut:
    expired = row.deleted_at is not None
    return RunArtifactOut(
        id=row.id,
        run_id=row.run_id,
        kind=row.kind,  # type: ignore[arg-type]
        content_type=row.content_type,
        bytes=row.bytes,
        node_id=row.node_id,
        step_index=row.step_index,
        filename=row.filename,
        note=row.note or ("产物已过期清理" if expired else None),
        deleted_at=row.deleted_at,
        created_at=row.created_at,
        expired=expired,
    )


def _list_item(
    run: Run,
    workflow_name: str,
    version_index: int,
    pending: Optional[PendingApproval] = None,
    db: Optional[Session] = None,
) -> RunListItem:
    duration_ms: Optional[int] = None
    if run.started_at and run.finished_at:
        duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
    err_summary: Optional[str] = None
    if run.error:
        from app.agents.autonomous_errors import is_technical_message, user_failure_message

        if getattr(run, "mode", "graph") == "autonomous" and is_technical_message(run.error):
            err_summary = user_failure_message(
                objective=getattr(run, "objective", "") or "",
                summary=run.error,
                reason=None,
            )[:200]
        else:
            err_summary = run.error[:200]
    return RunListItem(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_name=run_list_label(run, workflow_name),
        workflow_version_id=run.workflow_version_id,
        version_index=version_index,
        status=run.status,  # type: ignore[arg-type]
        mode=getattr(run, "mode", "graph") or "graph",  # type: ignore[arg-type]
        objective=getattr(run, "objective", None),
        queued_at=run.queued_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_ms=duration_ms,
        error_summary=err_summary,
        pending_approval=pending,
        queue_position=run_svc.queue_position(run.id),
        total_input_tokens=int(getattr(run, "total_input_tokens", 0) or 0),
        total_output_tokens=int(getattr(run, "total_output_tokens", 0) or 0),
        total_llm_calls=int(getattr(run, "total_llm_calls", 0) or 0),
        total_vision_calls=int(getattr(run, "total_vision_calls", 0) or 0),
        estimated_cost_usd=getattr(run, "estimated_cost_usd", None),
        cost_note=getattr(run, "cost_note", None),
        execution_mode=getattr(run, "execution_mode", "cloud") or "cloud",  # type: ignore[arg-type]
        worker_id=getattr(run, "worker_id", None),
        worker_name=_worker_name(db, getattr(run, "worker_id", None)),
        queue_reason=run_svc.queue_reason(run.id),
    )


@router.get("/api/runs/cost-summary", response_model=RunCostSummaryOut)
def get_runs_cost_summary(
    from_: datetime = Query(alias="from"),
    to: datetime = Query(),
    db: Session = Depends(get_session),
) -> RunCostSummaryOut:
    summary = cost_svc.window_cost_summary(from_ts=from_, to_ts=to, session=db)
    return RunCostSummaryOut.model_validate(summary)


@router.get("/api/runs", response_model=list[RunListItem])
def list_runs(
    workflow_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    sort: Optional[str] = Query(default=None),
    db: Session = Depends(get_session),
    _ctx: AuthContext = Depends(get_org_context),
) -> list[RunListItem]:
    stmt = select(Run).where(org_scope_filter(Run, _ctx.org_id, db))
    if workflow_id:
        stmt = stmt.where(Run.workflow_id == workflow_id)
    if sort == "cost":
        stmt = stmt.order_by(
            Run.estimated_cost_usd.desc().nulls_last(),  # type: ignore[attr-defined]
            Run.queued_at.desc(),  # type: ignore[attr-defined]
        )
    else:
        stmt = stmt.order_by(Run.queued_at.desc())  # type: ignore[attr-defined]
    stmt = stmt.offset(offset).limit(limit)
    runs = db.exec(stmt).all()
    pending_by_run = approvals_svc.pending_for_runs(db, [r.id for r in runs])

    items: list[RunListItem] = []
    for r in runs:
        wf = db.get(Workflow, r.workflow_id)
        wf_name = wf.name if wf else "(deleted)"
        v = db.get(WorkflowVersion, r.workflow_version_id)
        v_index = v.version_index if v else 0
        pending_row = pending_by_run.get(r.id)
        pending = (
            _pending_approval_out(pending_row) if pending_row is not None else None
        )
        items.append(_list_item(r, wf_name, v_index, pending, db))
    return items


@router.post("/api/runs", response_model=RunOut)
def create_run(
    body: dict = Body(...),
    db: Session = Depends(get_session),
    _ctx: AuthContext = Depends(get_org_context),
) -> RunOut:
    workflow_id = body.get("workflow_id")
    if not workflow_id:
        raise HTTPException(400, detail="workflow_id required")
    wf = db.get(Workflow, workflow_id)
    if wf is None:
        raise HTTPException(404, detail="workflow not found")
    require_org_match(wf.org_id, _ctx.org_id, db)
    version_id = body.get("version_id")
    browser_profile_id = body.get("browser_profile_id")
    browser_session_id = body.get("browser_session_id")
    parameters = body.get("parameters")
    totp_identifier = body.get("totp_identifier")
    record_video = body.get("record_video")
    execution_mode = body.get("execution_mode") or "cloud"
    worker_id = body.get("worker_id")
    worker_pool = body.get("worker_pool")
    try:
        run = run_svc.enqueue_run(
            workflow_id,
            db,
            version_id=version_id,
            browser_profile_id=browser_profile_id,
            browser_session_id=browser_session_id,
            parameters=parameters,
            totp_identifier=totp_identifier,
            record_video=record_video,
            execution_mode=execution_mode,
            worker_id=worker_id,
            worker_pool=worker_pool,
        )
    except param_svc.ParameterValidationError as exc:
        raise HTTPException(422, detail=str(exc))
    except run_svc.QueueFullError as exc:
        raise HTTPException(429, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc))
    return _run_to_out(run, db)


@router.post(
    "/api/workflows/{workflow_id}/runs", response_model=RunOut
)
def create_run_for_workflow(
    workflow_id: str,
    body: Optional[RunCreate] = None,
    db: Session = Depends(get_session),
    _ctx: AuthContext = Depends(get_org_context),
) -> RunOut:
    wf = db.get(Workflow, workflow_id)
    if wf is None:
        raise HTTPException(404, detail="workflow not found")
    require_org_match(wf.org_id, _ctx.org_id, db)
    profile_id = body.browser_profile_id if body is not None else None
    session_id = body.browser_session_id if body is not None else None
    parameters = body.parameters if body is not None else None
    totp_id = body.totp_identifier if body is not None else None
    record_video = body.record_video if body is not None else None
    execution_mode = body.execution_mode if body is not None else "cloud"
    worker_id = body.worker_id if body is not None else None
    worker_pool = body.worker_pool if body is not None else None
    try:
        run = run_svc.enqueue_run(
            workflow_id,
            db,
            browser_profile_id=profile_id,
            browser_session_id=session_id,
            parameters=parameters,
            totp_identifier=totp_id,
            record_video=record_video,
            execution_mode=execution_mode,
            worker_id=worker_id,
            worker_pool=worker_pool,
        )
    except param_svc.ParameterValidationError as exc:
        raise HTTPException(422, detail=str(exc))
    except run_svc.QueueFullError as exc:
        raise HTTPException(429, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc))
    return _run_to_out(run, db)


def get_run_impl(run_id: str, db: Session, org_id: str) -> RunReplayResponse:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, detail="run not found")
    require_org_match(run.org_id, org_id, db)
    version = db.get(WorkflowVersion, run.workflow_version_id)
    if version is None:
        raise HTTPException(404, detail="workflow version not found for run")
    events = db.exec(
        select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)
    ).all()
    event_models = []
    for e in events:
        payload = json.loads(e.payload_json)
        event_models.append(
            RunEventOut(
                id=e.id or 0,
                run_id=e.run_id,
                seq=e.seq,
                event_type=e.event_type,
                node_id=e.node_id,
                ts=e.ts,
                payload=payload,
            )
        )
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
        run=_run_to_out(run, db),
        workflow_version=version_out,
        events=event_models,
    )


@router.get(
    "/api/runs/{run_id}", response_model=RunReplayResponse
)
def get_run(
    run_id: str,
    db: Session = Depends(get_session),
    _ctx: AuthContext = Depends(get_org_context),
) -> RunReplayResponse:
    return get_run_impl(run_id, db, _ctx.org_id)


@router.get(
    "/api/runs/{run_id}/replay", response_model=RunReplayResponse
)
def get_run_replay(
    run_id: str,
    db: Session = Depends(get_session),
    _ctx: AuthContext = Depends(get_org_context),
) -> RunReplayResponse:
    return get_run_impl(run_id, db, _ctx.org_id)


@router.post(
    "/api/runs/{run_id}/abort", response_model=RunOut
)
def abort_run(run_id: str, db: Session = Depends(get_session)) -> RunOut:
    try:
        run = run_svc.request_abort(run_id)
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc))
    refreshed = db.get(Run, run_id) or run
    return _run_to_out(refreshed, db)


@router.get("/api/runs/{run_id}/input-files")
def list_run_input_files(
    run_id: str,
    db: Session = Depends(get_session),
    _ctx: AuthContext = Depends(get_org_context),
):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, detail="run not found")
    require_org_match(run.org_id, _ctx.org_id, db)
    return run_input_svc.list_run_input_files(run_id)


@router.get("/api/runs/{run_id}/input-files/{file_id}")
def get_run_input_file(
    run_id: str,
    file_id: str,
    db: Session = Depends(get_session),
    _ctx: AuthContext = Depends(get_org_context),
):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, detail="run not found")
    require_org_match(run.org_id, _ctx.org_id, db)
    path = run_input_svc.resolve_run_input_file(run_id, file_id)
    if path is None or not path.is_file():
        raise HTTPException(404, detail="input file not found")
    filename = path.name.split("_", 1)[-1] if "_" in path.name else path.name
    guessed, _ = mimetypes.guess_type(filename)
    return FileResponse(
        path=path,
        media_type=guessed or "application/octet-stream",
        filename=filename,
    )


@router.get("/api/runs/{run_id}/artifacts", response_model=list[RunArtifactOut])
def list_run_artifacts(
    run_id: str,
    kind: Optional[str] = Query(default=None),
    node_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_session),
) -> list[RunArtifactOut]:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, detail="run not found")
    if kind and kind not in artifact_svc.ARTIFACT_KINDS:
        raise HTTPException(400, detail=f"invalid kind: {kind}")
    rows = artifact_svc.list_artifacts(run_id, kind=kind, node_id=node_id, session=db)
    return [_artifact_to_out(r) for r in rows]


@router.get("/api/runs/{run_id}/artifacts/{artifact_id}")
def get_run_artifact(
    run_id: str,
    artifact_id: str,
    db: Session = Depends(get_session),
):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, detail="run not found")
    row = artifact_svc.get_artifact(artifact_id, run_id=run_id, session=db)
    if row is None:
        raise HTTPException(404, detail="artifact not found")
    if row.deleted_at is not None:
        return JSONResponse(
            status_code=410,
            content={
                "id": row.id,
                "kind": row.kind,
                "note": "产物已过期清理",
                "expired": True,
            },
        )
    file_path = artifact_svc.resolve_path(row)
    if not file_path.is_file() or row.bytes == 0:
        return JSONResponse(
            status_code=404,
            content={
                "id": row.id,
                "kind": row.kind,
                "note": row.note or "file unavailable",
            },
        )
    if row.kind == "llm_trace":
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            payload = None
        if isinstance(payload, dict):
            return JSONResponse(
                content=payload,
                media_type=row.content_type,
            )
    return FileResponse(
        path=file_path,
        media_type=row.content_type,
        filename=row.filename or file_path.name,
    )


@router.get("/api/runs/{run_id}/artifacts/{artifact_id}/thumbnail")
def get_run_artifact_thumbnail(
    run_id: str,
    artifact_id: str,
    db: Session = Depends(get_session),
):
    """Return a thumbnail for image artifacts (screenshots); falls back to full bytes."""
    row = artifact_svc.get_artifact(artifact_id, run_id=run_id, session=db)
    if row is None:
        raise HTTPException(404, detail="artifact not found")
    if row.deleted_at is not None:
        raise HTTPException(410, detail="产物已过期清理")
    if row.kind != "screenshot":
        raise HTTPException(400, detail="thumbnails only supported for screenshots")
    file_path = artifact_svc.resolve_path(row)
    if not file_path.is_file():
        raise HTTPException(404, detail="artifact file missing")
    return FileResponse(path=file_path, media_type=row.content_type)


__all__ = ["router"]
