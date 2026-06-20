from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from sqlmodel import Session, func, select

from app.db.models import Run, RunApproval, RunEvent
from app.db.session import engine

logger = logging.getLogger(__name__)

_events: dict[str, asyncio.Event] = {}


class ApprovalNotFound(Exception):
    pass


class ApprovalAlreadyResolved(Exception):
    pass


class ApprovalInputValidationError(Exception):
    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = errors
        super().__init__(str(errors))


class ApprovalWaitAborted(Exception):
    """Raised when an approval wait is cancelled by the run abort signal."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _next_seq(session: Session, run_id: str) -> int:
    current = session.exec(
        select(func.max(RunApproval.seq)).where(RunApproval.run_id == run_id)
    ).one()
    return int(current or 0) + 1


def _validate_inputs(schema: list[dict], inputs: dict[str, Any]) -> None:
    errors: dict[str, str] = {}
    for field in schema:
        name = field.get("name")
        if not name:
            continue
        required = bool(field.get("required"))
        ftype = field.get("type", "string")
        value = inputs.get(name)
        if required and (name not in inputs or value is None or value == ""):
            errors[name] = "required field missing"
            continue
        if name not in inputs or value is None:
            continue
        if ftype == "string" and not isinstance(value, str):
            errors[name] = "expected string"
        elif ftype == "number" and not isinstance(value, (int, float)):
            errors[name] = "expected number"
        elif ftype == "boolean" and not isinstance(value, bool):
            errors[name] = "expected boolean"
    if errors:
        raise ApprovalInputValidationError(errors)


def request(
    session: Session,
    *,
    run_id: str,
    node_id: str,
    prompt: str,
    inputs_schema: list[dict],
) -> RunApproval:
    approval = RunApproval(
        run_id=run_id,
        node_id=node_id,
        seq=_next_seq(session, run_id),
        prompt=prompt,
        inputs_schema=list(inputs_schema),
        requested_at=_utcnow(),
    )
    session.add(approval)
    session.commit()
    session.refresh(approval)
    _events[approval.id] = asyncio.Event()
    return approval


def pending_for_run(session: Session, run_id: str) -> Optional[RunApproval]:
    return session.exec(
        select(RunApproval)
        .where(RunApproval.run_id == run_id, RunApproval.decision.is_(None))  # type: ignore[union-attr]
        .order_by(RunApproval.seq.desc())  # type: ignore[attr-defined]
    ).first()


def latest_for_run_node(
    session: Session, run_id: str, node_id: str
) -> Optional[RunApproval]:
    return session.exec(
        select(RunApproval)
        .where(RunApproval.run_id == run_id, RunApproval.node_id == node_id)
        .order_by(RunApproval.seq.desc())  # type: ignore[attr-defined]
    ).first()


def pending_for_run_node(
    session: Session, run_id: str, node_id: str
) -> Optional[RunApproval]:
    return session.exec(
        select(RunApproval)
        .where(
            RunApproval.run_id == run_id,
            RunApproval.node_id == node_id,
            RunApproval.decision.is_(None),  # type: ignore[union-attr]
        )
        .order_by(RunApproval.seq.desc())  # type: ignore[attr-defined]
    ).first()


def pending_for_runs(
    session: Session, run_ids: list[str]
) -> dict[str, RunApproval]:
    if not run_ids:
        return {}
    rows = session.exec(
        select(RunApproval)
        .where(
            RunApproval.run_id.in_(run_ids),  # type: ignore[attr-defined]
            RunApproval.decision.is_(None),  # type: ignore[union-attr]
        )
        .order_by(RunApproval.run_id, RunApproval.seq.desc())  # type: ignore[attr-defined]
    ).all()
    out: dict[str, RunApproval] = {}
    for row in rows:
        if row.run_id not in out:
            out[row.run_id] = row
    return out


def resolve(
    session: Session,
    approval_id: str,
    decision: Literal["approve", "reject"],
    inputs: dict[str, Any],
) -> RunApproval:
    row = session.get(RunApproval, approval_id)
    if row is None:
        raise ApprovalNotFound(f"approval {approval_id!r} not found")
    if row.decision is not None:
        raise ApprovalAlreadyResolved("approval already resolved")
    payload_inputs = dict(inputs or {})
    if decision == "approve":
        _validate_inputs(row.inputs_schema or [], payload_inputs)
    else:
        payload_inputs = dict(inputs or {})
    row.decision = decision
    row.decision_inputs = payload_inputs
    row.resolved_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    event = _events.pop(approval_id, None)
    if event is not None:
        event.set()
    return row


def mark_lost(session: Session, approval_id: str) -> Optional[RunApproval]:
    row = session.get(RunApproval, approval_id)
    if row is None or row.decision is not None:
        return row
    row.decision = "lost"
    row.resolved_at = _utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    event = _events.pop(approval_id, None)
    if event is not None:
        event.set()
    return row


def mark_pending_lost_for_run(session: Session, run_id: str) -> Optional[RunApproval]:
    row = pending_for_run(session, run_id)
    if row is None:
        return None
    return mark_lost(session, row.id)


async def wait(
    approval_id: str,
    *,
    abort_event: Optional[asyncio.Event] = None,
) -> RunApproval:
    event = _events.get(approval_id)
    if event is None:
        with Session(engine) as session:
            row = session.get(RunApproval, approval_id)
            if row is None:
                raise ApprovalNotFound(f"approval {approval_id!r} not found")
            if row.decision is not None:
                return row
        event = asyncio.Event()
        _events[approval_id] = event

    if abort_event is not None and abort_event.is_set():
        raise ApprovalWaitAborted()

    if abort_event is None:
        await event.wait()
    else:
        wait_task = asyncio.create_task(event.wait())
        abort_task = asyncio.create_task(abort_event.wait())
        done, pending = await asyncio.wait(
            {wait_task, abort_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if abort_task in done:
            raise ApprovalWaitAborted()
        await wait_task

    with Session(engine) as session:
        row = session.get(RunApproval, approval_id)
        if row is None:
            raise ApprovalNotFound(f"approval {approval_id!r} not found")
        return row


def reap_lost_approvals_on_startup() -> int:
    """Mark stale pending approvals lost and fail their parent runs."""
    import json

    reaped = 0
    with Session(engine) as session:
        rows = session.exec(
            select(RunApproval, Run)
            .join(Run, Run.id == RunApproval.run_id)
            .where(
                RunApproval.decision.is_(None),  # type: ignore[union-attr]
                Run.status == "running",
            )
        ).all()
        for approval, run in rows:
            approval.decision = "lost"
            approval.resolved_at = _utcnow()
            session.add(approval)
            run.status = "failed"
            run.finished_at = _utcnow()
            run.error = "approval lost across backend restart"
            session.add(run)
            payload = {
                "event": "run_failed",
                "node_id": None,
                "ts": _utcnow().isoformat(),
                "error": "approval lost across backend restart",
                "reason": "approval lost across backend restart",
                "approval_id": approval.id,
            }
            seq_row = session.exec(
                select(func.max(RunEvent.seq)).where(RunEvent.run_id == run.id)
            ).one()
            next_seq = int(seq_row or 0) + 1
            session.add(
                RunEvent(
                    run_id=run.id,
                    seq=next_seq,
                    event_type="run_failed",
                    node_id=None,
                    ts=_utcnow(),
                    payload_json=json.dumps(payload, ensure_ascii=False),
                )
            )
            session.commit()
            _events.pop(approval.id, None)
            logger.warning(
                "reaped lost approval run=%s approval=%s node=%s",
                run.id,
                approval.id,
                approval.node_id,
            )
            reaped += 1
    return reaped


def clear_event(approval_id: str) -> None:
    _events.pop(approval_id, None)


__all__ = [
    "ApprovalAlreadyResolved",
    "ApprovalInputValidationError",
    "ApprovalNotFound",
    "ApprovalWaitAborted",
    "clear_event",
    "latest_for_run_node",
    "mark_lost",
    "mark_pending_lost_for_run",
    "pending_for_run",
    "pending_for_run_node",
    "pending_for_runs",
    "reap_lost_approvals_on_startup",
    "request",
    "resolve",
    "wait",
]
