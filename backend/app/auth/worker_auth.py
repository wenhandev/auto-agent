"""Worker session token authentication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, Query
from sqlmodel import Session

from app.db.models import Worker, WorkerSession
from app.db.session import get_session
from app.services import worker_sessions as worker_session_svc


@dataclass
class WorkerAuth:
    worker: Worker
    session: WorkerSession


def _extract_worker_token(
    authorization: Optional[str],
    x_worker_token: Optional[str],
    token: Optional[str],
) -> Optional[str]:
    if token and token.strip():
        return token.strip()
    if x_worker_token and x_worker_token.strip():
        return x_worker_token.strip()
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip()
    return None


def authenticate_worker_session(
    session: Session,
    *,
    authorization: Optional[str] = None,
    x_worker_token: Optional[str] = None,
    token: Optional[str] = None,
) -> WorkerAuth:
    plaintext = _extract_worker_token(authorization, x_worker_token, token)
    if not plaintext:
        raise HTTPException(status_code=401, detail="missing worker session token")
    looked_up = worker_session_svc.lookup_worker_by_token(session, plaintext)
    if looked_up is None:
        raise HTTPException(status_code=401, detail="invalid worker session token")
    worker, worker_session = looked_up
    return WorkerAuth(worker=worker, session=worker_session)


async def require_worker_session(
    authorization: Optional[str] = Header(default=None),
    x_worker_token: Optional[str] = Header(default=None, alias="x-worker-token"),
    token: Optional[str] = Query(default=None),
    session: Session = Depends(get_session),
) -> WorkerAuth:
    return authenticate_worker_session(
        session,
        authorization=authorization,
        x_worker_token=x_worker_token,
        token=token,
    )


__all__ = ["WorkerAuth", "authenticate_worker_session", "require_worker_session"]
