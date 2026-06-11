"""In-process APScheduler wrapper for cron triggers.

Source of truth is the `trigger` table; APScheduler holds a memory job
store rebuilt from that table at boot. Trigger CRUD reconciles individual
jobs via register_trigger / unregister_trigger.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from sqlmodel import Session, select

from app.db.models import Trigger
from app.db.session import engine


logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_scheduler() -> Optional[AsyncIOScheduler]:
    return _scheduler


def _job_id(trigger_id: str) -> str:
    return f"trigger:{trigger_id}"


def _fire_trigger(trigger_id: str) -> None:
    """Coroutine target for an APScheduler cron job. Sets last_fired_at
    then enqueues a run via the standard runs service."""
    from app.services import runs as run_svc

    with Session(engine) as session:
        trig = session.get(Trigger, trigger_id)
        if trig is None or not trig.enabled or trig.type != "cron":
            return
        workflow_id = trig.workflow_id
        trig.last_fired_at = _utcnow()
        trig.updated_at = _utcnow()
        session.add(trig)
        session.commit()

    try:
        run_svc.enqueue_run_standalone(
            workflow_id,
            source="cron",
            trigger_id=trigger_id,
        )
    except Exception:
        logger.exception(
            "cron fire failed: workflow=%s trigger=%s", workflow_id, trigger_id
        )


def register_trigger(trigger: Trigger) -> None:
    """Add or replace a single trigger job in the scheduler.

    Safe to call before scheduler.start(); APScheduler will hold pending
    jobs until start time. No-op if the trigger is not a cron type or is
    disabled.
    """
    if _scheduler is None:
        logger.warning("register_trigger called before init_scheduler")
        return
    if trigger.type != "cron":
        return
    job_id = _job_id(trigger.id)
    try:
        cron = CronTrigger.from_crontab(trigger.schedule_or_path)
    except Exception as exc:
        logger.warning(
            "skipping invalid cron expression %r for trigger=%s: %s",
            trigger.schedule_or_path,
            trigger.id,
            exc,
        )
        return
    if not trigger.enabled:
        try:
            _scheduler.remove_job(job_id)
        except Exception:
            pass
        return
    try:
        _scheduler.add_job(
            _fire_trigger,
            trigger=cron,
            id=job_id,
            args=[trigger.id],
            replace_existing=True,
            misfire_grace_time=60,
        )
        logger.info("registered cron trigger=%s expr=%r", trigger.id, trigger.schedule_or_path)
    except Exception:
        logger.exception("failed to register trigger=%s", trigger.id)


def unregister_trigger(trigger_id: str) -> None:
    if _scheduler is None:
        return
    try:
        _scheduler.remove_job(_job_id(trigger_id))
        logger.info("unregistered cron trigger=%s", trigger_id)
    except Exception:
        pass


def list_jobs() -> list[dict]:
    if _scheduler is None:
        return []
    out: list[dict] = []
    for job in _scheduler.get_jobs():
        out.append({
            "id": job.id,
            "next_run_time": (
                job.next_run_time.isoformat() if job.next_run_time else None
            ),
            "trigger": str(job.trigger),
        })
    return out


def init_scheduler(_app: FastAPI) -> None:
    """Build the singleton scheduler, register all enabled cron triggers,
    and start. Called from FastAPI lifespan after init_db()."""
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    with Session(engine) as session:
        rows = session.exec(
            select(Trigger).where(
                Trigger.type == "cron", Trigger.enabled.is_(True)  # type: ignore[attr-defined]
            )
        ).all()
    count = 0
    for trig in rows:
        try:
            register_trigger(trig)
            count += 1
        except Exception:
            logger.exception("failed to register trigger=%s on boot", trig.id)
    _scheduler.start()
    logger.info("scheduler started with %d cron jobs", count)


async def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
    except Exception:
        logger.exception("scheduler shutdown failed")
    _scheduler = None


__all__ = [
    "init_scheduler",
    "shutdown_scheduler",
    "register_trigger",
    "unregister_trigger",
    "get_scheduler",
    "list_jobs",
]
