from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db.models import Run
from app.db.session import get_session
from app.schemas_api import (
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    PendingApprovalOut,
)
from app.services import approvals as approvals_svc


router = APIRouter(tags=["approvals"])


def _pending_out(row) -> PendingApprovalOut:
    return PendingApprovalOut(
        id=row.id,
        run_id=row.run_id,
        node_id=row.node_id,
        seq=row.seq,
        prompt=row.prompt,
        inputs_schema=list(row.inputs_schema or []),
        requested_at=row.requested_at,
    )


@router.get(
    "/api/runs/{run_id}/approvals",
    response_model=list[PendingApprovalOut],
)
def list_pending_approvals(
    run_id: str, db: Session = Depends(get_session)
) -> list[PendingApprovalOut]:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, detail="run not found")
    row = approvals_svc.pending_for_run(db, run_id)
    if row is None:
        return []
    return [_pending_out(row)]


@router.post(
    "/api/runs/{run_id}/approvals/{node_id}",
    response_model=ApprovalDecisionResponse,
)
def resolve_approval(
    run_id: str,
    node_id: str,
    body: ApprovalDecisionRequest,
    db: Session = Depends(get_session),
) -> ApprovalDecisionResponse:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, detail="run not found")
    if run.status != "running":
        raise HTTPException(
            410,
            detail=f"run is no longer pending approval (status={run.status})",
        )
    pending = approvals_svc.pending_for_run_node(db, run_id, node_id)
    if pending is None:
        latest = approvals_svc.latest_for_run_node(db, run_id, node_id)
        if latest is not None and latest.decision is not None:
            raise HTTPException(409, detail="approval already resolved")
        raise HTTPException(404, detail="no pending approval for this node")
    try:
        resolved = approvals_svc.resolve(
            db, pending.id, body.decision, body.inputs
        )
    except approvals_svc.ApprovalAlreadyResolved:
        raise HTTPException(409, detail="approval already resolved")
    except approvals_svc.ApprovalInputValidationError as exc:
        raise HTTPException(422, detail=exc.errors)
    if getattr(run, "execution_mode", "cloud") == "worker":
        from app.services import worker_hub

        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(worker_hub.request_resume_on_worker(run_id))
        except RuntimeError:
            pass
    assert resolved.resolved_at is not None
    return ApprovalDecisionResponse(
        node_id=resolved.node_id,
        decision=resolved.decision,  # type: ignore[arg-type]
        inputs=dict(resolved.decision_inputs or {}),
        resolved_at=resolved.resolved_at,
    )


__all__ = ["router"]
