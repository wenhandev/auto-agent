"""Worker registry persistence helpers."""

from __future__ import annotations

import json
import socket
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from sqlmodel import Session, select

from app.db.models import Organization, User, Worker
from app.schemas_api import WorkerEnvironmentCheckOut, WorkerOut


DESKTOP_CLIENT_POLICIES = frozenset({"disabled", "approval_required", "open"})
APPROVAL_STATUSES = frozenset({"pending", "approved", "rejected"})

ApprovalStatus = Literal["pending", "approved", "rejected"]
DesktopClientPolicy = Literal["disabled", "approval_required", "open"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def default_hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


_GENERIC_CLIENT_LABELS = frozenset(
    {"localhost", "127.0.0.1", "unknown", "desktop", "my device"}
)


def normalize_client_label(label: Optional[str]) -> Optional[str]:
    """Drop generic hostnames so worker display names stay human-readable."""
    if not label:
        return None
    trimmed = label.strip()
    if not trimmed or trimmed.lower() in _GENERIC_CLIENT_LABELS:
        return None
    return trimmed


def effective_approval_status(worker: Worker) -> ApprovalStatus:
    """Backward compat: legacy rows without explicit status are treated as approved."""
    raw = worker.approval_status or "approved"
    if raw not in APPROVAL_STATUSES:
        return "approved"
    return raw  # type: ignore[return-value]


def effective_desktop_client_policy(org: Organization) -> DesktopClientPolicy:
    raw = org.desktop_client_policy or "approval_required"
    if raw not in DESKTOP_CLIENT_POLICIES:
        return "approval_required"
    return raw  # type: ignore[return-value]


def parse_tags(raw: Optional[str]) -> list[str]:
    if not raw:
        return ["default"]
    try:
        parsed = json.loads(raw)
    except Exception:
        return ["default"]
    if isinstance(parsed, list):
        return [str(x) for x in parsed if str(x).strip()] or ["default"]
    return ["default"]


def parse_checks(raw: Optional[str]) -> list[WorkerEnvironmentCheckOut]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    out: list[WorkerEnvironmentCheckOut] = []
    for item in parsed:
        if isinstance(item, dict) and item.get("id"):
            try:
                out.append(WorkerEnvironmentCheckOut.model_validate(item))
            except Exception:
                continue
    return out


def parse_capabilities(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def worker_to_out(
    session: Session,
    worker: Worker,
    *,
    active_runs: int = 0,
    org: Optional[Organization] = None,
) -> WorkerOut:
    user = session.get(User, worker.user_id)
    if org is None:
        org = session.get(Organization, worker.org_id)
    policy = effective_desktop_client_policy(org) if org else None
    return WorkerOut(
        id=worker.id,
        machine_id=worker.machine_id,
        display_name=worker.display_name,
        hostname=worker.hostname,
        user_id=worker.user_id,
        user_email=user.email if user else None,
        org_id=worker.org_id,
        status="online" if worker.status == "online" else "offline",
        tags=parse_tags(worker.tags_json),
        max_concurrent_runs=worker.max_concurrent_runs,
        active_runs=active_runs,
        agent_version=worker.agent_version,
        environment_status=worker.environment_status,  # type: ignore[arg-type]
        environment_checks=parse_checks(worker.environment_checks_json),
        capabilities=parse_capabilities(worker.capabilities_json),
        last_seen_at=worker.last_seen_at,
        created_at=worker.created_at,
        revoked_at=worker.revoked_at,
        approval_status=effective_approval_status(worker),
        approved_at=worker.approved_at,
        approved_by_user_id=worker.approved_by_user_id,
        desktop_client_policy=policy,
    )


def apply_login_approval(
    session: Session,
    worker: Worker,
    org: Organization,
    *,
    is_new: bool,
) -> Worker:
    policy = effective_desktop_client_policy(org)
    current = effective_approval_status(worker)

    if policy == "open":
        if current != "approved":
            worker.approval_status = "approved"
            worker.approved_at = _utcnow()
    elif policy == "approval_required":
        if is_new:
            worker.approval_status = "pending"
        elif current == "approved":
            pass
        elif current == "rejected":
            pass
        else:
            worker.approval_status = "pending"

    session.add(worker)
    session.commit()
    session.refresh(worker)
    return worker


def upsert_worker(
    session: Session,
    *,
    org_id: str,
    user_id: str,
    machine_id: str,
    display_name: Optional[str] = None,
    hostname: Optional[str] = None,
    tags: Optional[list[str]] = None,
    agent_version: Optional[str] = None,
    environment: Optional[dict[str, Any]] = None,
) -> tuple[Worker, bool]:
    row = session.exec(
        select(Worker).where(
            Worker.org_id == org_id,
            Worker.user_id == user_id,
            Worker.machine_id == machine_id,
        )
    ).first()
    is_new = row is None
    tags_json = json.dumps(tags or ["default"], ensure_ascii=False)
    host = normalize_client_label(hostname) or normalize_client_label(
        default_hostname()
    ) or "desktop"
    display = normalize_client_label(display_name)
    env_status = "unknown"
    env_checks_json: Optional[str] = None
    caps_json: Optional[str] = None
    if environment:
        env_status = str(environment.get("environment_status") or "unknown")
        checks = environment.get("checks")
        if isinstance(checks, list):
            env_checks_json = json.dumps(checks, ensure_ascii=False, default=str)
        caps = environment.get("capabilities")
        if isinstance(caps, dict):
            caps_json = json.dumps(caps, ensure_ascii=False, default=str)

    if row is None:
        row = Worker(
            machine_id=machine_id,
            display_name=display or host,
            hostname=host,
            org_id=org_id,
            user_id=user_id,
            tags_json=tags_json,
            agent_version=agent_version,
            environment_status=env_status,
            environment_checks_json=env_checks_json,
            capabilities_json=caps_json,
        )
    else:
        if display:
            row.display_name = display
        elif not normalize_client_label(row.display_name):
            row.display_name = host
        row.hostname = host
        row.tags_json = tags_json
        if agent_version:
            row.agent_version = agent_version
        if environment:
            row.environment_status = env_status
            if env_checks_json is not None:
                row.environment_checks_json = env_checks_json
            if caps_json is not None:
                row.capabilities_json = caps_json
    session.add(row)
    session.commit()
    session.refresh(row)
    return row, is_new


def list_workers(session: Session, *, org_id: str) -> list[Worker]:
    return list(
        session.exec(
            select(Worker)
            .where(Worker.org_id == org_id, Worker.revoked_at.is_(None))  # type: ignore[union-attr]
            .order_by(Worker.created_at.desc())  # type: ignore[attr-defined]
        ).all()
    )


def get_worker_for_org(session: Session, worker_id: str, *, org_id: str) -> Worker:
    row = session.get(Worker, worker_id)
    if row is None or row.org_id != org_id:
        raise ValueError("worker not found")
    return row


def approve_worker(
    session: Session,
    worker_id: str,
    *,
    org_id: str,
    approved_by_user_id: str,
) -> Worker:
    row = get_worker_for_org(session, worker_id, org_id=org_id)
    row.approval_status = "approved"
    row.approved_at = _utcnow()
    row.approved_by_user_id = approved_by_user_id
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def reject_worker(session: Session, worker_id: str, *, org_id: str) -> Worker:
    row = get_worker_for_org(session, worker_id, org_id=org_id)
    row.approval_status = "rejected"
    row.approved_at = None
    row.approved_by_user_id = None
    session.add(row)
    session.commit()
    session.refresh(row)
    from app.services import worker_sessions as ws_svc

    ws_svc.revoke_worker_sessions(session, worker_id)
    return row


def revoke_worker(session: Session, worker_id: str, *, org_id: str) -> Worker:
    row = get_worker_for_org(session, worker_id, org_id=org_id)
    row.revoked_at = _utcnow()
    row.status = "offline"
    session.add(row)
    session.commit()
    session.refresh(row)
    from app.services import worker_sessions as ws_svc

    ws_svc.revoke_worker_sessions(session, worker_id)
    return row


def update_worker_environment(
    session: Session,
    worker_id: str,
    environment: dict[str, Any],
    *,
    agent_version: str | None = None,
) -> None:
    row = session.get(Worker, worker_id)
    if row is None:
        return
    row.environment_status = str(environment.get("environment_status") or row.environment_status)
    checks = environment.get("checks")
    if isinstance(checks, list):
        row.environment_checks_json = json.dumps(checks, ensure_ascii=False, default=str)
    caps = environment.get("capabilities")
    if isinstance(caps, dict):
        row.capabilities_json = json.dumps(caps, ensure_ascii=False, default=str)
    if agent_version:
        row.agent_version = agent_version
    elif isinstance(caps, dict) and caps.get("agent_version"):
        row.agent_version = str(caps["agent_version"])
    row.last_seen_at = _utcnow()
    session.add(row)
    session.commit()


def set_worker_status(session: Session, worker_id: str, status: str) -> None:
    row = session.get(Worker, worker_id)
    if row is None:
        return
    row.status = status
    row.last_seen_at = _utcnow()
    session.add(row)
    session.commit()


def is_worker_execution_allowed(worker: Worker) -> bool:
    if worker.revoked_at is not None:
        return False
    return effective_approval_status(worker) == "approved"


__all__ = [
    "APPROVAL_STATUSES",
    "DESKTOP_CLIENT_POLICIES",
    "default_hostname",
    "effective_approval_status",
    "effective_desktop_client_policy",
    "worker_to_out",
    "apply_login_approval",
    "upsert_worker",
    "list_workers",
    "get_worker_for_org",
    "approve_worker",
    "reject_worker",
    "revoke_worker",
    "update_worker_environment",
    "set_worker_status",
    "is_worker_execution_allowed",
]
