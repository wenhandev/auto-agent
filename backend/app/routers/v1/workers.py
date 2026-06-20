"""Worker login and registry (v1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from app.auth.authorization import require_min_role
from app.auth.context import AuthContext, get_org_context
from app.auth.session import check_login_rate_limit
from app.auth.worker_auth import WorkerAuth, require_worker_session
from app.db.models import OrgMembership, Organization, User
from app.db.session import get_session
from app.schemas_api import WorkerLoginRequest, WorkerLoginResponse, WorkerOut
from app.services import orgs as org_svc
from app.services import worker_hub
from app.services import worker_sessions as worker_session_svc
from app.services import workers as worker_svc
from app.services.orgs import verify_password


router = APIRouter(prefix="/workers", tags=["workers"])


def _resolve_org_for_user(session: Session, user: User) -> tuple[str, str]:
    default_org = org_svc.ensure_bootstrap(session)
    role = org_svc.lookup_membership_role(session, user.id, default_org.id)
    if role is not None:
        return default_org.id, role
    membership = session.exec(
        select(OrgMembership)
        .where(OrgMembership.user_id == user.id)
        .order_by(OrgMembership.created_at)  # type: ignore[arg-type]
    ).first()
    if membership is None:
        raise HTTPException(status_code=403, detail="no organisation membership")
    return membership.org_id, membership.role


@router.post("/login", response_model=WorkerLoginResponse)
def worker_login(
    body: WorkerLoginRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> WorkerLoginResponse:
    client_ip = request.client.host if request.client else "unknown"
    check_login_rate_limit(f"worker-login:{client_ip}:{body.email.lower()}")

    user = session.exec(
        select(User).where(User.email == body.email.strip().lower())
    ).first()
    if user is None or not user.password_hash:
        raise HTTPException(status_code=401, detail="invalid credentials")
    if user.disabled_at is not None:
        raise HTTPException(status_code=401, detail="invalid credentials")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")

    org_id, _role = _resolve_org_for_user(session, user)
    org = session.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=403, detail="no organisation membership")

    policy = worker_svc.effective_desktop_client_policy(org)
    if policy == "disabled":
        raise HTTPException(
            status_code=403,
            detail="clients are disabled for this organisation",
        )

    worker, is_new = worker_svc.upsert_worker(
        session,
        org_id=org_id,
        user_id=user.id,
        machine_id=body.machine_id.strip(),
        display_name=body.display_name,
        hostname=body.hostname,
        tags=body.tags,
        agent_version=body.agent_version,
        environment=body.environment,
    )
    worker = worker_svc.apply_login_approval(session, worker, org, is_new=is_new)
    worker_session, token = worker_session_svc.create_worker_session(
        session, worker_id=worker.id
    )
    return WorkerLoginResponse(
        worker_session_token=token,
        worker_id=worker.id,
        org_id=org_id,
        expires_at=worker_session.expires_at,
        approval_status=worker_svc.effective_approval_status(worker),
        desktop_client_policy=policy,
    )


@router.get("/me", response_model=WorkerOut)
def worker_me(
    session: Session = Depends(get_session),
    auth: WorkerAuth = Depends(require_worker_session),
) -> WorkerOut:
    org = session.get(Organization, auth.worker.org_id)
    active = worker_hub.active_run_count(auth.worker.id)
    return worker_svc.worker_to_out(
        session, auth.worker, active_runs=active, org=org
    )


@router.get("/", response_model=list[WorkerOut])
def list_workers_v1(
    session: Session = Depends(get_session),
    ctx: AuthContext = Depends(get_org_context),
) -> list[WorkerOut]:
    org = session.get(Organization, ctx.org_id)
    rows = worker_svc.list_workers(session, org_id=ctx.org_id)
    out: list[WorkerOut] = []
    for row in rows:
        active = worker_hub.active_run_count(row.id)
        out.append(
            worker_svc.worker_to_out(session, row, active_runs=active, org=org)
        )
    return out


@router.post("/{worker_id}/approve", response_model=WorkerOut)
def approve_worker_v1(
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
    active = worker_hub.active_run_count(row.id)
    return worker_svc.worker_to_out(session, row, active_runs=active, org=org)


@router.post("/{worker_id}/reject", response_model=WorkerOut)
def reject_worker_v1(
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
def revoke_worker_v1(
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
