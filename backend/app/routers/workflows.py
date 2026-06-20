from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import func
from sqlmodel import Session, select

from app.auth.authorization import (
    effective_role,
    require_min_role,
    require_workflow_visible,
    workflow_visibility_filter,
)
from app.auth.context import AuthContext, get_org_context, org_scope_filter, require_org_match

from app.db.crypto import decrypt
from app.db.models import (
    ChatMessage,
    ChatSession,
    Credential,
    Run,
    Trigger,
    Workflow,
    WorkflowCredential,
    WorkflowVersion,
)
from app.db.session import get_session
from app.schemas_api import (
    CredentialListItem,
    LastOutputShapesResponse,
    SelectorCacheStatsOut,
    StagingFileOut,
    WorkflowCreate,
    WorkflowCredentialLinkRequest,
    WorkflowListItem,
    WorkflowOut,
    WorkflowUpdate,
    WorkflowVersionCreate,
    WorkflowVersionOut,
)
from app.services import run_inputs as run_input_svc
from app.services import workflows as workflow_svc
from app.services.autonomous_workflows import is_hidden_workflow
from app.services import selector_cache as cache_svc


router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _version_to_out(version: WorkflowVersion) -> WorkflowVersionOut:
    return WorkflowVersionOut(
        id=version.id,
        workflow_id=version.workflow_id,
        version_index=version.version_index,
        authored_by=version.authored_by if version.authored_by in ("planner", "editor", "manual") else "manual",  # type: ignore[arg-type]
        workflow=workflow_svc.workflow_json_of(version),  # type: ignore[arg-type]
        created_at=version.created_at,
    )


def _workflow_to_out(workflow: Workflow, session: Session) -> WorkflowOut:
    current: WorkflowVersionOut | None = None
    if workflow.current_version_id:
        v = session.get(WorkflowVersion, workflow.current_version_id)
        if v is not None:
            current = _version_to_out(v)
    chat = workflow_svc.ensure_chat_session(workflow.id, session)
    return WorkflowOut(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        current_version=current,
        chat_session_id=chat.id,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
    )


def list_workflows_impl(
    session: Session,
    org_id: str,
    *,
    user_id: str | None = None,
    role: str = "member",
) -> list[WorkflowListItem]:
    scope = org_scope_filter(Workflow, org_id, session)
    visibility = workflow_visibility_filter(
        Workflow, user_id=user_id, role=role
    )
    workflows = session.exec(
        select(Workflow)
        .where(scope, visibility)
        .order_by(Workflow.updated_at.desc())  # type: ignore[attr-defined]
    ).all()
    items: list[WorkflowListItem] = []
    for wf in workflows:
        if is_hidden_workflow(wf):
            continue
        current_index = None
        if wf.current_version_id:
            v = session.get(WorkflowVersion, wf.current_version_id)
            if v is not None:
                current_index = v.version_index
        last_run = session.exec(
            select(Run)
            .where(Run.workflow_id == wf.id)
            .order_by(Run.queued_at.desc())  # type: ignore[attr-defined]
        ).first()
        items.append(
            WorkflowListItem(
                id=wf.id,
                name=wf.name,
                description=wf.description,
                current_version_index=current_index,
                last_run_status=last_run.status if last_run else None,  # type: ignore[arg-type]
                updated_at=wf.updated_at,
            )
        )
    return items


@router.get("", response_model=list[WorkflowListItem])
def list_workflows(
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> list[WorkflowListItem]:
    return list_workflows_impl(
        session,
        ctx.org_id,
        user_id=ctx.user_id,
        role=effective_role(ctx),
    )


def create_workflow_for_org(
    body: WorkflowCreate,
    session: Session,
    org_id: str,
    *,
    created_by: str | None = None,
) -> WorkflowOut:
    workflow = workflow_svc.create_workflow(
        name=body.name,
        session=session,
        description=body.description,
        authored_by="manual",
        org_id=org_id,
        created_by=created_by,
    )
    return _workflow_to_out(workflow, session)


@router.post("", response_model=WorkflowOut)
def create_workflow(
    body: WorkflowCreate,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> WorkflowOut:
    return create_workflow_for_org(
        body, session, ctx.org_id, created_by=ctx.user_id
    )


def get_workflow_for_org(
    workflow_id: str,
    session: Session,
    org_id: str,
    ctx: AuthContext | None = None,
) -> WorkflowOut:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow not found")
    require_org_match(workflow.org_id, org_id, session)
    if ctx is not None:
        require_workflow_visible(workflow, ctx)
    return _workflow_to_out(workflow, session)


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(
    workflow_id: str,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> WorkflowOut:
    return get_workflow_for_org(workflow_id, session, ctx.org_id, ctx=ctx)


def update_workflow_for_org(
    workflow_id: str,
    body: WorkflowUpdate,
    session: Session,
    org_id: str,
) -> WorkflowOut:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow not found")
    require_org_match(workflow.org_id, org_id, session)
    if body.name is not None:
        workflow.name = body.name
    if body.description is not None:
        workflow.description = body.description
    workflow.updated_at = _utcnow()
    session.add(workflow)
    session.commit()
    session.refresh(workflow)
    return _workflow_to_out(workflow, session)


@router.patch("/{workflow_id}", response_model=WorkflowOut)
@router.put("/{workflow_id}", response_model=WorkflowOut)
def update_workflow(
    workflow_id: str,
    body: WorkflowUpdate,
    session: Session = Depends(get_session),
    _ctx: AuthContext = Depends(get_org_context),
) -> WorkflowOut:
    return update_workflow_for_org(workflow_id, body, session, _ctx.org_id)


def delete_workflow_for_org(
    workflow_id: str,
    session: Session,
    org_id: str,
    ctx: AuthContext | None = None,
) -> dict:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow not found")
    require_org_match(workflow.org_id, org_id, session)
    if ctx is not None:
        require_workflow_visible(workflow, ctx)
        require_min_role(ctx, "member")

    runs = session.exec(select(Run).where(Run.workflow_id == workflow_id)).all()
    for run in runs:
        session.delete(run)
    triggers = session.exec(
        select(Trigger).where(Trigger.workflow_id == workflow_id)
    ).all()
    if triggers:
        from app.services import scheduler as scheduler_svc

        for trig in triggers:
            if trig.type in ("cron", "poll"):
                scheduler_svc.unregister_trigger(trig.id)
            session.delete(trig)
    sessions = session.exec(
        select(ChatSession).where(ChatSession.workflow_id == workflow_id)
    ).all()
    for cs in sessions:
        msgs = session.exec(
            select(ChatMessage).where(ChatMessage.session_id == cs.id)
        ).all()
        for m in msgs:
            session.delete(m)
        session.delete(cs)
    workflow.current_version_id = None
    session.add(workflow)
    session.flush()
    versions = session.exec(
        select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow_id)
    ).all()
    for v in versions:
        session.delete(v)
    session.delete(workflow)
    session.commit()
    return {"ok": True}


@router.delete("/{workflow_id}")
def delete_workflow(
    workflow_id: str,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> dict:
    return delete_workflow_for_org(workflow_id, session, ctx.org_id, ctx=ctx)


def _workflow_for_org(
    session: Session,
    workflow_id: str,
    org_id: str,
    ctx: AuthContext | None = None,
) -> Workflow:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow not found")
    require_org_match(workflow.org_id, org_id, session)
    if ctx is not None:
        require_workflow_visible(workflow, ctx)
    return workflow


@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersionOut])
def list_versions(
    workflow_id: str,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> list[WorkflowVersionOut]:
    _workflow_for_org(session, workflow_id, ctx.org_id, ctx=ctx)
    versions = session.exec(
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow_id)
        .order_by(WorkflowVersion.version_index)
    ).all()
    return [_version_to_out(v) for v in versions]


@router.post(
    "/{workflow_id}/versions",
    response_model=WorkflowVersionOut,
)
def create_version(
    workflow_id: str,
    body: WorkflowVersionCreate,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> WorkflowVersionOut:
    _workflow_for_org(session, workflow_id, ctx.org_id, ctx=ctx)
    try:
        version = workflow_svc.save_new_version(
            workflow_id,
            body.workflow.model_dump(),
            body.authored_by,
            session,
        )
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    return _version_to_out(version)


@router.get(
    "/{workflow_id}/versions/{version_id}",
    response_model=WorkflowVersionOut,
)
def get_version(
    workflow_id: str,
    version_id: str,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> WorkflowVersionOut:
    _workflow_for_org(session, workflow_id, ctx.org_id, ctx=ctx)
    version = session.get(WorkflowVersion, version_id)
    if version is None or version.workflow_id != workflow_id:
        raise HTTPException(404, detail="workflow version not found")
    return _version_to_out(version)


def _decrypt_field_names(cred: Credential) -> list[str]:
    try:
        plain = decrypt(cred.ciphertext)
    except Exception:
        return []
    try:
        import json as _json

        data = _json.loads(plain.decode("utf-8"))
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    return [str(k) for k in data.keys()]


def _credential_to_list_item(
    cred: Credential, usage_count: int
) -> CredentialListItem:
    return CredentialListItem(
        id=cred.id,
        name=cred.name,
        description=cred.description,
        field_names=_decrypt_field_names(cred),
        updated_at=cred.updated_at,
        usage_count=usage_count,
    )


def _usage_count_for(credential_id: str, session: Session) -> int:
    row = session.exec(
        select(func.count(WorkflowCredential.id)).where(
            WorkflowCredential.credential_id == credential_id
        )
    ).one()
    if isinstance(row, tuple):
        return int(row[0])
    return int(row)


@router.get(
    "/{workflow_id}/credentials", response_model=list[CredentialListItem]
)
def list_workflow_credentials(
    workflow_id: str,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> list[CredentialListItem]:
    _workflow_for_org(session, workflow_id, ctx.org_id, ctx=ctx)
    links = session.exec(
        select(WorkflowCredential).where(
            WorkflowCredential.workflow_id == workflow_id
        )
    ).all()
    items: list[CredentialListItem] = []
    for link in links:
        cred = session.get(Credential, link.credential_id)
        if cred is None:
            continue
        usage = _usage_count_for(cred.id, session)
        items.append(_credential_to_list_item(cred, usage))
    items.sort(key=lambda i: i.name)
    return items


@router.post(
    "/{workflow_id}/credentials", response_model=CredentialListItem
)
def link_workflow_credential(
    workflow_id: str,
    body: WorkflowCredentialLinkRequest,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> CredentialListItem:
    workflow = _workflow_for_org(session, workflow_id, ctx.org_id, ctx=ctx)
    cred = session.get(Credential, body.credential_id)
    if cred is None:
        raise HTTPException(404, detail="credential not found")
    require_org_match(cred.org_id, ctx.org_id, session)
    existing = session.exec(
        select(WorkflowCredential).where(
            WorkflowCredential.workflow_id == workflow_id,
            WorkflowCredential.credential_id == body.credential_id,
        )
    ).first()
    if existing is not None:
        raise HTTPException(
            409, detail="credential already linked to this workflow"
        )
    link = WorkflowCredential(
        workflow_id=workflow_id,
        credential_id=body.credential_id,
        created_at=_utcnow(),
    )
    session.add(link)
    workflow.updated_at = _utcnow()
    session.add(workflow)
    session.commit()
    usage = _usage_count_for(cred.id, session)
    return _credential_to_list_item(cred, usage)


@router.delete("/{workflow_id}/credentials/{credential_id}")
def unlink_workflow_credential(
    workflow_id: str,
    credential_id: str,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> Response:
    workflow = _workflow_for_org(session, workflow_id, ctx.org_id, ctx=ctx)
    link = session.exec(
        select(WorkflowCredential).where(
            WorkflowCredential.workflow_id == workflow_id,
            WorkflowCredential.credential_id == credential_id,
        )
    ).first()
    if link is None:
        raise HTTPException(404, detail="credential not linked to workflow")
    session.delete(link)
    workflow.updated_at = _utcnow()
    session.add(workflow)
    session.commit()
    return Response(status_code=204)


@router.post(
    "/{workflow_id}/input-files",
    response_model=StagingFileOut,
)
async def upload_run_input_file(
    workflow_id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> StagingFileOut:
    _workflow_for_org(session, workflow_id, ctx.org_id, ctx=ctx)
    filename = file.filename or "upload.bin"
    try:
        data = await file.read()
        meta = run_input_svc.store_staging_file(
            workflow_id,
            data,
            filename=filename,
            content_type=file.content_type,
        )
    except run_input_svc.RunInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return StagingFileOut.model_validate(meta)


@router.get("/{workflow_id}/last-output-shapes", response_model=LastOutputShapesResponse)
def get_last_output_shapes(
    workflow_id: str,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> LastOutputShapesResponse:
    _workflow_for_org(session, workflow_id, ctx.org_id, ctx=ctx)

    from app.services.last_output_shapes import fetch_last_output_shapes

    data = fetch_last_output_shapes(session, workflow_id)
    return LastOutputShapesResponse(
        run_id=data.run_id,
        started_at=data.started_at,
        shapes=data.shapes,
    )


@router.get("/{workflow_id}/selector-cache", response_model=SelectorCacheStatsOut)
def get_selector_cache_stats(
    workflow_id: str,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> SelectorCacheStatsOut:
    _workflow_for_org(session, workflow_id, ctx.org_id, ctx=ctx)
    stats = cache_svc.get_cache_stats(session, workflow_id)
    return SelectorCacheStatsOut(
        workflow_id=stats.workflow_id,
        entry_count=stats.entry_count,
        total_hits=stats.total_hits,
        total_misses=stats.total_misses,
        entries=stats.entries,
    )


@router.delete("/{workflow_id}/selector-cache")
def clear_selector_cache(
    workflow_id: str,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> dict:
    _workflow_for_org(session, workflow_id, ctx.org_id, ctx=ctx)
    removed = cache_svc.clear_workflow_cache(session, workflow_id)
    return {"ok": True, "removed": removed}


__all__ = ["router"]
