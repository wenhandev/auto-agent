"""Public workflow endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.auth.api_key import require_api_key
from app.auth.context import current_auth, require_org_match
from app.db.models import ApiKey, Workflow
from app.db.session import get_session
from app.routers.runs import _run_to_out
from app.schemas_api import RunCreate, RunOut, WorkflowCreate, WorkflowListItem, WorkflowOut, WorkflowUpdate
from app.services import runs as run_svc
from app.services import workflow_parameters as param_svc


router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("", response_model=list[WorkflowListItem])
def list_workflows_v1(
    session: Session = Depends(get_session),
    _auth: ApiKey = Depends(require_api_key),
) -> list[WorkflowListItem]:
    from app.auth.authorization import effective_role
    from app.routers.workflows import list_workflows_impl

    ctx = current_auth()
    return list_workflows_impl(
        session,
        ctx.org_id,
        user_id=ctx.user_id,
        role=effective_role(ctx),
    )


@router.post("", response_model=WorkflowOut, status_code=201)
def create_workflow_v1(
    body: WorkflowCreate,
    session: Session = Depends(get_session),
    _auth: ApiKey = Depends(require_api_key),
) -> WorkflowOut:
    from app.routers.workflows import create_workflow_for_org

    ctx = current_auth()
    return create_workflow_for_org(
        body, session, ctx.org_id, created_by=ctx.user_id
    )


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow_v1(
    workflow_id: str,
    session: Session = Depends(get_session),
    _auth: ApiKey = Depends(require_api_key),
) -> WorkflowOut:
    from app.routers.workflows import get_workflow_for_org

    ctx = current_auth()
    return get_workflow_for_org(workflow_id, session, ctx.org_id, ctx=ctx)


@router.patch("/{workflow_id}", response_model=WorkflowOut)
def update_workflow_v1(
    workflow_id: str,
    body: WorkflowUpdate,
    session: Session = Depends(get_session),
    _auth: ApiKey = Depends(require_api_key),
) -> WorkflowOut:
    from app.routers.workflows import update_workflow_for_org

    return update_workflow_for_org(workflow_id, body, session, current_auth().org_id)


@router.delete("/{workflow_id}")
def delete_workflow_v1(
    workflow_id: str,
    session: Session = Depends(get_session),
    _auth: ApiKey = Depends(require_api_key),
) -> dict:
    from app.routers.workflows import delete_workflow_for_org

    ctx = current_auth()
    return delete_workflow_for_org(workflow_id, session, ctx.org_id, ctx=ctx)


@router.post("/{workflow_id}/run", response_model=RunOut, status_code=202)
def run_workflow_v1(
    workflow_id: str,
    body: Optional[RunCreate] = None,
    session: Session = Depends(get_session),
    api_key: ApiKey = Depends(require_api_key),
) -> RunOut:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow not found")
    require_org_match(workflow.org_id, current_auth().org_id, session)
    profile_id = body.browser_profile_id if body is not None else None
    parameters = body.parameters if body is not None else None
    totp_id = body.totp_identifier if body is not None else None
    record_video = body.record_video if body is not None else None
    execution_mode = (
        body.execution_mode if body is not None and body.execution_mode is not None
        else run_svc.default_execution_mode()
    )
    worker_id = body.worker_id if body is not None else None
    worker_pool = body.worker_pool if body is not None else None
    try:
        run = run_svc.enqueue_run(
            workflow_id,
            session,
            source="api",
            trigger_context={"kind": "api", "api_key_id": api_key.id},
            browser_profile_id=profile_id,
            parameters=parameters,
            totp_identifier=totp_id,
            record_video=record_video,
            execution_mode=execution_mode,
            worker_id=worker_id,
            worker_pool=worker_pool,
        )
    except param_svc.ParameterValidationError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    except run_svc.QueueFullError as exc:
        raise HTTPException(429, detail=str(exc)) from exc
    except run_svc.CloudExecutionDisabledError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    return _run_to_out(run, session)


__all__ = ["router"]
