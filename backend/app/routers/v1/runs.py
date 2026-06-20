"""Public run endpoints."""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.auth.api_key import require_api_key
from app.auth.context import current_auth, org_scope_filter
from app.db.models import ApiKey, Run, Workflow, WorkflowVersion
from app.db.session import get_session
from app.routers.runs import _run_to_out
from app.schemas_api import RunListItem, RunListPage, RunOut, RunReplayResponse
from app.services import approvals as approvals_svc
from app.services import runs as run_svc
from app.services import workflow_parameters as param_svc


router = APIRouter(prefix="/runs", tags=["runs"])


def _pending_out(row):
    from app.routers.runs import _pending_approval_out

    return _pending_approval_out(row)


def _list_item(run: Run, workflow_name: str, version_index: int, pending=None, db=None) -> RunListItem:
    from app.routers.runs import _list_item as _internal_list_item

    return _internal_list_item(run, workflow_name, version_index, pending, db)


def _encode_cursor(queued_at: datetime, run_id: str) -> str:
    payload = {"queued_at": queued_at.isoformat(), "id": run_id}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    pad = "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(cursor + pad)
        payload = json.loads(raw.decode("utf-8"))
        queued_at = datetime.fromisoformat(payload["queued_at"])
        run_id = str(payload["id"])
    except Exception as exc:
        raise HTTPException(400, detail="invalid cursor") from exc
    return queued_at, run_id


@router.get("", response_model=RunListPage)
def list_runs_v1(
    workflow_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: Optional[str] = Query(default=None),
    db: Session = Depends(get_session),
    _auth: ApiKey = Depends(require_api_key),
) -> RunListPage:
    org_id = current_auth().org_id
    stmt = select(Run).where(org_scope_filter(Run, org_id, db))
    if workflow_id:
        stmt = stmt.where(Run.workflow_id == workflow_id)
    if cursor:
        cur_queued_at, cur_id = _decode_cursor(cursor)
        stmt = stmt.where(
            (Run.queued_at < cur_queued_at)
            | ((Run.queued_at == cur_queued_at) & (Run.id < cur_id))
        )
    stmt = stmt.order_by(Run.queued_at.desc(), Run.id.desc()).limit(limit + 1)  # type: ignore[attr-defined]
    runs = list(db.exec(stmt).all())
    next_cursor: Optional[str] = None
    if len(runs) > limit:
        last = runs[limit - 1]
        next_cursor = _encode_cursor(last.queued_at, last.id)
        runs = runs[:limit]

    pending_by_run = approvals_svc.pending_for_runs(db, [r.id for r in runs])
    items: list[RunListItem] = []
    for r in runs:
        wf = db.get(Workflow, r.workflow_id)
        wf_name = wf.name if wf else "(deleted)"
        v = db.get(WorkflowVersion, r.workflow_version_id)
        v_index = v.version_index if v else 0
        pending_row = pending_by_run.get(r.id)
        pending = _pending_out(pending_row) if pending_row is not None else None
        items.append(_list_item(r, wf_name, v_index, pending, db))
    return RunListPage(items=items, next_cursor=next_cursor)


@router.get("/{run_id}", response_model=RunReplayResponse)
def get_run_v1(
    run_id: str,
    db: Session = Depends(get_session),
    _auth: ApiKey = Depends(require_api_key),
) -> RunReplayResponse:
    from app.routers.runs import get_run_impl

    return get_run_impl(run_id, db, current_auth().org_id)


@router.post("/{run_id}/cancel", response_model=RunOut)
def cancel_run_v1(
    run_id: str,
    db: Session = Depends(get_session),
    _auth: ApiKey = Depends(require_api_key),
) -> RunOut:
    try:
        run = run_svc.request_abort(run_id)
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    refreshed = db.get(Run, run_id) or run
    return _run_to_out(refreshed, db)


__all__ = ["router"]
