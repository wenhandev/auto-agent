"""Session-authenticated worker registry for the web UI."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.auth.authorization import require_min_role
from app.auth.context import AuthContext, get_org_context
from app.db.models import Organization
from app.db.session import get_session
from app.schemas_api import WorkerOut
from app.services import worker_hub
from app.services import workers as worker_svc


router = APIRouter(prefix="/api/workers", tags=["workers"])


@router.get("", response_model=list[WorkerOut])
def list_workers(
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> list[WorkerOut]:
    org = session.get(Organization, ctx.org_id)
    rows = worker_svc.list_workers(session, org_id=ctx.org_id)
    return [
        worker_svc.worker_to_out(
            session,
            row,
            active_runs=worker_hub.active_run_count(row.id),
            org=org,
        )
        for row in rows
    ]


@router.post("/{worker_id}/approve", response_model=WorkerOut)
def approve_worker(
    worker_id: str,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> WorkerOut:
    require_min_role(ctx, "admin")
    org = session.get(Organization, ctx.org_id)
    try:
        row = worker_svc.approve_worker(
            session,
            worker_id,
            org_id=ctx.org_id,
            approved_by_user_id=ctx.user_id or "",
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="worker not found") from None
    return worker_svc.worker_to_out(
        session,
        row,
        active_runs=worker_hub.active_run_count(row.id),
        org=org,
    )


@router.post("/{worker_id}/reject", response_model=WorkerOut)
def reject_worker(
    worker_id: str,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> WorkerOut:
    require_min_role(ctx, "admin")
    org = session.get(Organization, ctx.org_id)
    try:
        row = worker_svc.reject_worker(session, worker_id, org_id=ctx.org_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="worker not found") from None
    return worker_svc.worker_to_out(session, row, active_runs=0, org=org)


@router.post("/{worker_id}/revoke", response_model=WorkerOut)
def revoke_worker(
    worker_id: str,
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> WorkerOut:
    org = session.get(Organization, ctx.org_id)
    try:
        row = worker_svc.revoke_worker(session, worker_id, org_id=ctx.org_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="worker not found") from None
    return worker_svc.worker_to_out(session, row, active_runs=0, org=org)


__all__ = ["router"]
