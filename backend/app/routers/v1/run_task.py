"""Public run-task entry point."""

from __future__ import annotations

import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.auth.api_key import require_api_key
from app.db.models import ApiKey
from app.db.session import get_session
from app.schemas_api import RunTaskRequest, RunTaskResponse
from app.services import runs as run_svc
from app.services import workflow_parameters as param_svc
from app.services import workflows as workflow_svc


router = APIRouter(tags=["run-task"])


def _build_run_task_workflow(*, prompt: str, url: Optional[str], max_steps: int) -> dict:
    nodes: list[dict] = [
        {
            "id": "start",
            "type": "start",
            "label": "Start",
            "params": {},
        }
    ]
    edges: list[dict] = []
    prev_id = "start"

    if url:
        goto_id = "goto"
        nodes.append(
            {
                "id": goto_id,
                "type": "goto_url",
                "label": "Open URL",
                "params": {"url": url},
            }
        )
        edges.append({"id": "e-goto", "source": prev_id, "target": goto_id})
        prev_id = goto_id

    vn_id = "vision"
    nodes.append(
        {
            "id": vn_id,
            "type": "vision_navigate",
            "label": "Run task",
            "params": {"goal": prompt, "max_steps": max_steps},
        }
    )
    edges.append({"id": "e-vision", "source": prev_id, "target": vn_id})

    return {
        "nodes": nodes,
        "edges": edges,
        "start_id": "start",
        "parameters": [],
    }


@router.post("/run-task", response_model=RunTaskResponse, status_code=202)
def run_task(
    body: RunTaskRequest,
    session: Session = Depends(get_session),
    api_key: ApiKey = Depends(require_api_key),
) -> RunTaskResponse:
    wf_json = _build_run_task_workflow(
        prompt=body.prompt,
        url=body.url,
        max_steps=body.max_steps,
    )
    name = f"run-task-{uuid.uuid4().hex[:8]}"
    workflow = workflow_svc.create_workflow(
        name=name,
        session=session,
        description=f"Ephemeral run-task: {body.prompt[:120]}",
        initial_workflow_json=wf_json,
        authored_by="manual",
    )

    trigger_context: dict = {"kind": "api", "api_key_id": api_key.id}
    if body.browser_session_id:
        trigger_context["browser_session_id"] = body.browser_session_id
    if body.data_schema:
        trigger_context["data_schema"] = body.data_schema

    try:
        run = run_svc.enqueue_run(
            workflow.id,
            session,
            source="api",
            trigger_context=trigger_context,
            browser_profile_id=body.browser_profile_id,
            browser_session_id=body.browser_session_id,
            totp_identifier=body.totp_identifier,
        )
    except param_svc.ParameterValidationError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    except run_svc.QueueFullError as exc:
        raise HTTPException(429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc)) from exc

    if not body.persist:
        workflow.status = "archived"
        session.add(workflow)
        session.commit()

    if body.data_schema and not run.data_schema_json:
        run.data_schema_json = json.dumps(body.data_schema, ensure_ascii=False)
        session.add(run)
        session.commit()
        session.refresh(run)

    return RunTaskResponse(run_id=run.id, status=run.status)  # type: ignore[arg-type]


__all__ = ["router"]
