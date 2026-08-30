"""REST API for autonomous tasks."""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db.models import Run
from app.db.session import get_session
from app.schemas_api import TaskCreate, TaskDistillOut, TaskOut, TaskResultOut
from app.services.trajectory_distillation import distill_task_run
from app.schemas_tasks import TaskSpec
from app.services import tasks as task_svc


router = APIRouter(tags=["tasks"])


def _run_to_task_out(run: Run) -> TaskOut:
    allowed_domains: Optional[list[str]] = None
    if run.allowed_domains_json:
        allowed_domains = json.loads(run.allowed_domains_json)
    allowed_tools: Optional[list[str]] = None
    if run.allowed_tools_json:
        allowed_tools = json.loads(run.allowed_tools_json)
    data_schema: Optional[dict[str, Any]] = None
    if run.data_schema_json:
        data_schema = json.loads(run.data_schema_json)
    result = task_svc.get_task_result(run)
    return TaskOut(
        id=run.id,
        mode=run.mode,  # type: ignore[arg-type]
        status=run.status,  # type: ignore[arg-type]
        objective=run.objective or "",
        start_url=run.start_url,
        max_steps=run.max_steps or 30,
        max_seconds=run.max_seconds or 300,
        success_criteria=run.success_criteria,
        allowed_domains=allowed_domains,
        data_schema=data_schema,
        require_confirmation=bool(run.require_confirmation),
        allowed_tools=allowed_tools,
        queued_at=run.queued_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error=run.error,
        result=TaskResultOut.model_validate(result.model_dump()) if result else None,
    )


@router.post("/api/tasks", response_model=TaskOut)
def create_task(body: TaskCreate, db: Session = Depends(get_session)) -> TaskOut:
    from app.services import runs as run_svc

    execution_mode = body.execution_mode or run_svc.default_execution_mode()
    try:
        run_svc.assert_execution_mode_allowed(execution_mode)
    except run_svc.CloudExecutionDisabledError as exc:
        raise HTTPException(400, detail=str(exc)) from exc

    spec = TaskSpec(
        objective=body.objective,
        start_url=body.start_url,
        max_steps=body.max_steps,
        max_seconds=body.max_seconds,
        success_criteria=body.success_criteria,
        allowed_domains=body.allowed_domains,
        data_schema=body.data_schema,
        require_confirmation=body.require_confirmation,
        allowed_tools=body.allowed_tools,
        synthesize_workflow=body.synthesize_workflow,
    )
    run = task_svc.create_task(db, spec, execution_mode=execution_mode)
    return _run_to_task_out(run)


@router.get("/api/tasks/{run_id}", response_model=TaskOut)
def get_task(run_id: str, db: Session = Depends(get_session)) -> TaskOut:
    run = db.get(Run, run_id)
    if run is None or run.mode != "autonomous":
        raise HTTPException(404, detail="task run not found")
    return _run_to_task_out(run)


def _proposal_out(row) -> "RouteSkillProposalOut":
    from app.schemas_api import RouteSkillProposalOut

    return RouteSkillProposalOut(
        id=row.id,
        source_type=row.source_type,
        source_id=row.source_id,
        org_id=row.org_id,
        domain=row.domain,
        capability=row.capability,
        url_pattern=row.url_pattern,
        prompt=row.prompt,
        status=row.status,  # type: ignore[arg-type]
        adopted_route_skill_id=row.adopted_route_skill_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/api/tasks/{run_id}/distill-route-skills", response_model=TaskDistillOut)
def distill_task_route_skills(
    run_id: str,
    db: Session = Depends(get_session),
) -> TaskDistillOut:
    try:
        result = distill_task_run(db, run_id)
    except ValueError as exc:
        msg = str(exc)
        code = 404 if "not found" in msg else 409
        raise HTTPException(code, detail=msg) from exc
    except Exception as exc:
        raise HTTPException(422, detail=f"distillation failed: {exc}") from exc

    segments = [
        {
            "domain": segment.domain,
            "url_pattern": segment.url_pattern,
            "capability": segment.capability,
            "event_count": len(segment.events),
        }
        for segment in result.segments
    ]
    return TaskDistillOut(
        run_id=run_id,
        distill_mode=result.mode,
        segments=segments,
        workflow=result.workflow_graph,
        route_skill_proposals=[_proposal_out(p) for p in result.proposals],
    )


__all__ = ["router"]
