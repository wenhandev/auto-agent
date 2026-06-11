from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db.models import ChatMessage, ChatSession, Workflow, WorkflowVersion
from app.db.session import get_session
from app.schemas_api import (
    ChatMessageOut,
    ChatTurnRequest,
    ChatTurnResponse,
    PatchOp,
    WorkflowVersionOut,
)
from app.services import workflows as workflow_svc
from app.services.chat import EditorAgent, EditorResponse, apply_patch


logger = logging.getLogger(__name__)


router = APIRouter(tags=["chat"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _msg_to_out(msg: ChatMessage) -> ChatMessageOut:
    return ChatMessageOut(
        id=msg.id,
        session_id=msg.session_id,
        role=msg.role,  # type: ignore[arg-type]
        content=msg.content,
        workflow_version_id=msg.workflow_version_id,
        created_at=msg.created_at,
    )


def _version_to_out(version: WorkflowVersion) -> WorkflowVersionOut:
    authored = version.authored_by if version.authored_by in ("planner", "editor", "manual") else "manual"
    return WorkflowVersionOut(
        id=version.id,
        workflow_id=version.workflow_id,
        version_index=version.version_index,
        authored_by=authored,  # type: ignore[arg-type]
        workflow=workflow_svc.workflow_json_of(version),  # type: ignore[arg-type]
        created_at=version.created_at,
    )


def _workflow_for_session(session_id: str, db: Session) -> tuple[ChatSession, Workflow]:
    cs = db.get(ChatSession, session_id)
    if cs is None:
        raise HTTPException(404, detail="chat session not found")
    workflow = db.get(Workflow, cs.workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow for session not found")
    return cs, workflow


async def _run_editor_turn(
    workflow_id: str,
    chat_session_id: str,
    user_message: str,
    db: Session,
) -> ChatTurnResponse:
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow not found")
    current_version = workflow_svc.get_current_version(workflow_id, db)
    if current_version is None:
        raise HTTPException(400, detail="workflow has no current version")
    current_json = workflow_svc.workflow_json_of(current_version)

    user_row = ChatMessage(
        session_id=chat_session_id,
        role="user",
        content=user_message,
        created_at=_utcnow(),
    )
    db.add(user_row)
    db.commit()
    db.refresh(user_row)

    history = db.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == chat_session_id)
        .order_by(ChatMessage.created_at)
    ).all()
    history_pairs: list[tuple[str, str]] = [(m.role, m.content) for m in history[:-1]]

    editor = EditorAgent()
    try:
        result: EditorResponse = await editor.edit(current_json, history_pairs, user_message)
    except Exception as exc:
        logger.exception("editor agent failed")
        assistant_row = ChatMessage(
            session_id=chat_session_id,
            role="assistant",
            content=f"编辑助手暂时不可用: {exc}",
            created_at=_utcnow(),
        )
        db.add(assistant_row)
        db.commit()
        db.refresh(assistant_row)
        return ChatTurnResponse(
            assistant_message=_msg_to_out(assistant_row),
            patch=None,
            new_version=None,
        )

    new_version: WorkflowVersion | None = None
    patch_ops: list[dict] | None = None
    extra_error: str | None = None

    if result.patch and result.full_workflow:
        extra_error = "editor returned both patch and full_workflow; ignoring both"
    elif result.patch:
        try:
            new_json = apply_patch(current_json, result.patch)
            new_version = workflow_svc.save_new_version(
                workflow_id=workflow_id,
                new_workflow_json=new_json,
                authored_by="editor",
                session=db,
            )
            patch_ops = result.patch
        except Exception as exc:
            extra_error = f"patch apply failed: {exc}"
    elif result.full_workflow:
        try:
            new_version = workflow_svc.save_new_version(
                workflow_id=workflow_id,
                new_workflow_json=result.full_workflow,
                authored_by="editor",
                session=db,
            )
        except Exception as exc:
            extra_error = f"full workflow apply failed: {exc}"

    content = result.assistant_message or ""
    if extra_error:
        content = f"{content}\n\n[note] {extra_error}".strip()

    assistant_row = ChatMessage(
        session_id=chat_session_id,
        role="assistant",
        content=content,
        workflow_version_id=new_version.id if new_version else None,
        created_at=_utcnow(),
    )
    db.add(assistant_row)
    db.commit()
    db.refresh(assistant_row)

    patch_models: list[PatchOp] | None = None
    if patch_ops:
        try:
            patch_models = [PatchOp.validate_python(op) if hasattr(PatchOp, "validate_python") else op for op in patch_ops]  # type: ignore[assignment]
        except Exception:
            patch_models = None

    return ChatTurnResponse(
        assistant_message=_msg_to_out(assistant_row),
        patch=patch_ops,  # type: ignore[arg-type]
        new_version=_version_to_out(new_version) if new_version else None,
    )


@router.get(
    "/api/chat/{session_id}", response_model=list[ChatMessageOut]
)
def get_chat_history(
    session_id: str, db: Session = Depends(get_session)
) -> list[ChatMessageOut]:
    cs = db.get(ChatSession, session_id)
    if cs is None:
        raise HTTPException(404, detail="chat session not found")
    rows = db.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    ).all()
    return [_msg_to_out(r) for r in rows]


@router.post(
    "/api/chat/{session_id}/messages", response_model=ChatTurnResponse
)
async def post_chat_message(
    session_id: str,
    body: ChatTurnRequest,
    db: Session = Depends(get_session),
) -> ChatTurnResponse:
    cs, workflow = _workflow_for_session(session_id, db)
    return await _run_editor_turn(workflow.id, cs.id, body.message, db)


@router.get(
    "/api/workflows/{workflow_id}/chat", response_model=list[ChatMessageOut]
)
def get_workflow_chat(
    workflow_id: str, db: Session = Depends(get_session)
) -> list[ChatMessageOut]:
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow not found")
    cs = workflow_svc.ensure_chat_session(workflow_id, db)
    rows = db.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == cs.id)
        .order_by(ChatMessage.created_at)
    ).all()
    return [_msg_to_out(r) for r in rows]


@router.post(
    "/api/workflows/{workflow_id}/chat", response_model=ChatTurnResponse
)
async def post_workflow_chat(
    workflow_id: str,
    body: ChatTurnRequest,
    db: Session = Depends(get_session),
) -> ChatTurnResponse:
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow not found")
    cs = workflow_svc.ensure_chat_session(workflow_id, db)
    return await _run_editor_turn(workflow_id, cs.id, body.message, db)


__all__ = ["router"]
