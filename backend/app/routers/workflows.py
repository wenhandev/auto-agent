from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func
from sqlmodel import Session, select

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
    WorkflowCreate,
    WorkflowCredentialLinkRequest,
    WorkflowListItem,
    WorkflowOut,
    WorkflowUpdate,
    WorkflowVersionOut,
)
from app.services import workflows as workflow_svc


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


@router.get("", response_model=list[WorkflowListItem])
def list_workflows(session: Session = Depends(get_session)) -> list[WorkflowListItem]:
    workflows = session.exec(
        select(Workflow).order_by(Workflow.updated_at.desc())  # type: ignore[attr-defined]
    ).all()
    items: list[WorkflowListItem] = []
    for wf in workflows:
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


@router.post("", response_model=WorkflowOut)
def create_workflow(
    body: WorkflowCreate, session: Session = Depends(get_session)
) -> WorkflowOut:
    workflow = workflow_svc.create_workflow(
        name=body.name,
        session=session,
        description=body.description,
        authored_by="manual",
    )
    return _workflow_to_out(workflow, session)


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(
    workflow_id: str, session: Session = Depends(get_session)
) -> WorkflowOut:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow not found")
    return _workflow_to_out(workflow, session)


@router.patch("/{workflow_id}", response_model=WorkflowOut)
@router.put("/{workflow_id}", response_model=WorkflowOut)
def update_workflow(
    workflow_id: str,
    body: WorkflowUpdate,
    session: Session = Depends(get_session),
) -> WorkflowOut:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow not found")
    if body.name is not None:
        workflow.name = body.name
    if body.description is not None:
        workflow.description = body.description
    workflow.updated_at = _utcnow()
    session.add(workflow)
    session.commit()
    session.refresh(workflow)
    return _workflow_to_out(workflow, session)


@router.delete("/{workflow_id}")
def delete_workflow(
    workflow_id: str, session: Session = Depends(get_session)
) -> dict:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow not found")

    runs = session.exec(select(Run).where(Run.workflow_id == workflow_id)).all()
    for run in runs:
        session.delete(run)
    triggers = session.exec(
        select(Trigger).where(Trigger.workflow_id == workflow_id)
    ).all()
    if triggers:
        from app.services import scheduler as scheduler_svc

        for trig in triggers:
            if trig.type == "cron":
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


@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersionOut])
def list_versions(
    workflow_id: str, session: Session = Depends(get_session)
) -> list[WorkflowVersionOut]:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow not found")
    versions = session.exec(
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow_id)
        .order_by(WorkflowVersion.version_index)
    ).all()
    return [_version_to_out(v) for v in versions]


@router.get(
    "/{workflow_id}/versions/{version_id}",
    response_model=WorkflowVersionOut,
)
def get_version(
    workflow_id: str,
    version_id: str,
    session: Session = Depends(get_session),
) -> WorkflowVersionOut:
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
    workflow_id: str, session: Session = Depends(get_session)
) -> list[CredentialListItem]:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow not found")
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
) -> CredentialListItem:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow not found")
    cred = session.get(Credential, body.credential_id)
    if cred is None:
        raise HTTPException(404, detail="credential not found")
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
) -> Response:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow not found")
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


__all__ = ["router"]
