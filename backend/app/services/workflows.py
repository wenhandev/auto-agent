from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from app.db.models import ChatSession, Workflow, WorkflowVersion
from app.schemas import Workflow as WorkflowSchema


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def workflow_json_of(version: WorkflowVersion) -> dict:
    return {
        "nodes": json.loads(version.nodes_json),
        "edges": json.loads(version.edges_json),
        "start_id": version.start_id,
    }


def load_workflow_schema(version: WorkflowVersion) -> WorkflowSchema:
    return WorkflowSchema.model_validate(workflow_json_of(version))


def _next_version_index(workflow_id: str, session: Session) -> int:
    rows = session.exec(
        select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow_id)
    ).all()
    if not rows:
        return 1
    return max(r.version_index for r in rows) + 1


def _empty_workflow_json() -> dict:
    return {
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "label": "开始",
                "params": {},
            }
        ],
        "edges": [],
        "start_id": "start",
    }


def create_workflow(
    name: str,
    session: Session,
    *,
    description: Optional[str] = None,
    initial_workflow_json: Optional[dict] = None,
    authored_by: str = "manual",
) -> Workflow:
    wf_json = initial_workflow_json or _empty_workflow_json()
    WorkflowSchema.model_validate(wf_json)

    workflow = Workflow(
        name=name,
        description=description,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    session.add(workflow)
    session.flush()

    version = WorkflowVersion(
        workflow_id=workflow.id,
        version_index=1,
        nodes_json=json.dumps(wf_json["nodes"], ensure_ascii=False),
        edges_json=json.dumps(wf_json["edges"], ensure_ascii=False),
        start_id=wf_json["start_id"],
        authored_by=authored_by,
        created_at=_utcnow(),
    )
    session.add(version)
    session.flush()

    workflow.current_version_id = version.id
    workflow.updated_at = _utcnow()
    session.add(workflow)

    chat = ChatSession(workflow_id=workflow.id, created_at=_utcnow())
    session.add(chat)

    session.commit()
    session.refresh(workflow)
    return workflow


def save_new_version(
    workflow_id: str,
    new_workflow_json: dict,
    authored_by: str,
    session: Session,
) -> WorkflowVersion:
    WorkflowSchema.model_validate(new_workflow_json)

    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise ValueError(f"workflow {workflow_id!r} not found")

    index = _next_version_index(workflow_id, session)
    version = WorkflowVersion(
        workflow_id=workflow_id,
        version_index=index,
        nodes_json=json.dumps(new_workflow_json["nodes"], ensure_ascii=False),
        edges_json=json.dumps(new_workflow_json["edges"], ensure_ascii=False),
        start_id=new_workflow_json["start_id"],
        authored_by=authored_by,
        created_at=_utcnow(),
    )
    session.add(version)
    session.flush()

    workflow.current_version_id = version.id
    workflow.updated_at = _utcnow()
    session.add(workflow)
    session.commit()
    session.refresh(version)
    return version


def get_current_version(workflow_id: str, session: Session) -> Optional[WorkflowVersion]:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None or workflow.current_version_id is None:
        return None
    return session.get(WorkflowVersion, workflow.current_version_id)


def ensure_chat_session(workflow_id: str, session: Session) -> ChatSession:
    chat = session.exec(
        select(ChatSession).where(ChatSession.workflow_id == workflow_id)
    ).first()
    if chat is not None:
        return chat
    chat = ChatSession(workflow_id=workflow_id, created_at=_utcnow())
    session.add(chat)
    session.commit()
    session.refresh(chat)
    return chat


__all__ = [
    "create_workflow",
    "save_new_version",
    "get_current_version",
    "ensure_chat_session",
    "workflow_json_of",
    "load_workflow_schema",
]
