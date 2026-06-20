"""Bounded idempotency store for app webhook event delivery."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlmodel import Session, select

from app.db.models import ProcessedEvent
from app.db.session import engine

logger = logging.getLogger(__name__)

_RETENTION = timedelta(days=7)
_MAX_ROWS_PER_TRIGGER = 5000


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sweep(session: Session, trigger_id: str) -> None:
    cutoff = _utcnow() - _RETENTION
    session.exec(
        delete(ProcessedEvent).where(
            ProcessedEvent.trigger_id == trigger_id,
            ProcessedEvent.processed_at < cutoff,
        )
    )
    rows = session.exec(
        select(ProcessedEvent)
        .where(ProcessedEvent.trigger_id == trigger_id)
        .order_by(ProcessedEvent.processed_at.desc())  # type: ignore[attr-defined]
    ).all()
    if len(rows) > _MAX_ROWS_PER_TRIGGER:
        for row in rows[_MAX_ROWS_PER_TRIGGER:]:
            session.delete(row)


def is_processed(trigger_id: str, event_id: str) -> bool:
    with Session(engine) as session:
        row = session.exec(
            select(ProcessedEvent).where(
                ProcessedEvent.trigger_id == trigger_id,
                ProcessedEvent.event_id == event_id,
            )
        ).first()
        return row is not None


def mark_processed(trigger_id: str, event_id: str) -> None:
    with Session(engine) as session:
        existing = session.exec(
            select(ProcessedEvent).where(
                ProcessedEvent.trigger_id == trigger_id,
                ProcessedEvent.event_id == event_id,
            )
        ).first()
        if existing is not None:
            return
        session.add(
            ProcessedEvent(
                trigger_id=trigger_id,
                event_id=event_id,
                processed_at=_utcnow(),
            )
        )
        _sweep(session, trigger_id)
        session.commit()


__all__ = ["is_processed", "mark_processed"]
