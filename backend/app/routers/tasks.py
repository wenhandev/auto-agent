"""REST API for autonomous tasks."""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db.models import Run
from app.db.session import get_session
from app.schemas_api import TaskCreate, TaskOut, TaskResultOut
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
    run = task_svc.create_task(db, spec)
    return _run_to_task_out(run)


@router.get("/api/tasks/{run_id}", response_model=TaskOut)
def get_task(run_id: str, db: Session = Depends(get_session)) -> TaskOut:
    run = db.get(Run, run_id)
    if run is None or run.mode != "autonomous":
        raise HTTPException(404, detail="task run not found")
    return _run_to_task_out(run)


__all__ = ["router"]
