"""Worker session token generation and validation."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Session, select

from app.db.models import Worker, WorkerSession
from app.settings import settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def generate_session_token() -> tuple[str, str, str]:
    token = secrets.token_urlsafe(32)
    full = f"wk_sess_{token}"
    return full, hash_token(full), f"{full[:16]}…"


def create_worker_session(session: Session, *, worker_id: str) -> tuple[WorkerSession, str]:
    full, token_hash, prefix = generate_session_token()
    expires_at = _utcnow() + timedelta(days=max(1, settings.worker_session_ttl_days))
    row = WorkerSession(
        worker_id=worker_id,
        token_hash=token_hash,
        prefix=prefix,
        expires_at=expires_at,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row, full


def lookup_worker_by_token(session: Session, plaintext: str) -> Optional[tuple[Worker, WorkerSession]]:
    if not plaintext.startswith("wk_sess_"):
        return None
    token_hash = hash_token(plaintext)
    ws = session.exec(
        select(WorkerSession).where(
            WorkerSession.token_hash == token_hash,
            WorkerSession.revoked_at.is_(None),  # type: ignore[union-attr]
        )
    ).first()
    if ws is None:
        return None
    exp = ws.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < _utcnow():
        return None
    worker = session.get(Worker, ws.worker_id)
    if worker is None or worker.revoked_at is not None:
        return None
    return worker, ws


def revoke_worker_sessions(session: Session, worker_id: str) -> int:
    now = _utcnow()
    rows = session.exec(
        select(WorkerSession).where(
            WorkerSession.worker_id == worker_id,
            WorkerSession.revoked_at.is_(None),  # type: ignore[union-attr]
        )
    ).all()
    for row in rows:
        row.revoked_at = now
        session.add(row)
    session.commit()
    return len(rows)


__all__ = [
    "hash_token",
    "generate_session_token",
    "create_worker_session",
    "lookup_worker_by_token",
    "revoke_worker_sessions",
]
