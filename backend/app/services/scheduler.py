"""In-process APScheduler wrapper for cron triggers.

Source of truth is the `trigger` table; APScheduler holds a memory job
store rebuilt from that table at boot. Trigger CRUD reconciles individual
jobs via register_trigger / unregister_trigger.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI
from sqlmodel import Session, select

from app.db.models import Trigger
from app.db.session import engine
from app.services import trigger_scheduling as sched_svc
from app.settings import settings


logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_scheduler() -> Optional[AsyncIOScheduler]:
    return _scheduler


def _job_id(trigger_id: str) -> str:
    return f"trigger:{trigger_id}"


def _poll_job_id(trigger_id: str) -> str:
    return f"poll:{trigger_id}"


async def _poll_trigger(trigger_id: str) -> None:
    from app.services import poll_runner as poll_svc

    try:
        await poll_svc.tick_trigger(trigger_id)
    except Exception:
        logger.exception("poll tick failed trigger=%s", trigger_id)


def _job_next_run_time(job: Any) -> Optional[datetime]:
    return getattr(job, "next_run_time", None)


def refresh_next_run_at(trigger_id: str) -> None:
    """Persist ``next_run_at`` from the cron expression (no scheduler job required)."""
    with Session(engine) as session:
        trig = session.get(Trigger, trigger_id)
        if trig is None or trig.type != "cron":
            return
        if not trig.enabled:
            trig.next_run_at = None
        else:
            tz = trig.timezone or sched_svc.DEFAULT_TIMEZONE
            fires = sched_svc.compute_next_fires(trig.schedule_or_path, tz, n=1)
            trig.next_run_at = fires[0] if fires else None
        trig.updated_at = _utcnow()
        session.add(trig)
        session.commit()


def _persist_next_run_at(trigger_id: str) -> None:
    next_at: Optional[datetime] = None
    if _scheduler is not None:
        job = _scheduler.get_job(_job_id(trigger_id))
        next_at = _job_next_run_time(job) if job is not None else None
    with Session(engine) as session:
        trig = session.get(Trigger, trigger_id)
        if trig is None:
            return
        if next_at is None and trig.type == "cron":
            tz = trig.timezone or sched_svc.DEFAULT_TIMEZONE
            fires = sched_svc.compute_next_fires(trig.schedule_or_path, tz, n=1)
            next_at = fires[0] if fires else None
        trig.next_run_at = next_at
        trig.updated_at = _utcnow()
        session.add(trig)
        session.commit()


def _fire_trigger(trigger_id: str) -> None:
    """Coroutine target for an APScheduler cron job. Sets last_fired_at
    then enqueues a run via the standard runs service."""
    from app.services import runs as run_svc

    with Session(engine) as session:
        trig = session.get(Trigger, trigger_id)
        if trig is None or not trig.enabled or trig.type != "cron":
            return
        workflow_id = trig.workflow_id
        parameters_json = trig.parameters_json
        trig.last_fired_at = _utcnow()
        trig.updated_at = _utcnow()
        session.add(trig)
        session.commit()

    try:
        params: Optional[dict[str, Any]] = None
        if parameters_json:
            try:
                parsed = json.loads(parameters_json)
                if isinstance(parsed, dict):
                    params = parsed
            except Exception:
                logger.exception(
                    "cron trigger parameters_json unreadable trigger=%s", trigger_id
                )
        run_svc.enqueue_run_standalone(
            workflow_id,
            source="cron",
            trigger_id=trigger_id,
            parameters=params,
        )
        _persist_next_run_at(trigger_id)
    except Exception:
        logger.exception(
            "cron fire failed: workflow=%s trigger=%s", workflow_id, trigger_id
        )


def register_trigger(trigger: Trigger) -> None:
    """Add or replace a single trigger job in the scheduler.

    Safe to call before scheduler.start(); APScheduler will hold pending
    jobs until start time. No-op if the trigger is not a cron/poll type or is
    disabled.
    """
    if _scheduler is None:
        logger.warning("register_trigger called before init_scheduler")
        return
    if trigger.type == "cron":
        _register_cron_trigger(trigger)
    elif trigger.type == "poll":
        _register_poll_trigger(trigger)


def _register_cron_trigger(trigger: Trigger) -> None:
    if _scheduler is None:
        return
    job_id = _job_id(trigger.id)
    tz = trigger.timezone or sched_svc.DEFAULT_TIMEZONE
    try:
        cron = CronTrigger.from_crontab(trigger.schedule_or_path, timezone=tz)
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
        _clear_next_run_at(trigger.id)
        return
    grace = sched_svc.misfire_grace_time(trigger.misfire_policy or "skip")
    try:
        _scheduler.add_job(
            _fire_trigger,
            trigger=cron,
            id=job_id,
            args=[trigger.id],
            replace_existing=True,
            misfire_grace_time=grace,
            coalesce=trigger.misfire_policy != "catch_up",
        )
        logger.info(
            "registered cron trigger=%s expr=%r tz=%s policy=%s",
            trigger.id,
            trigger.schedule_or_path,
            tz,
            trigger.misfire_policy,
        )
        _persist_next_run_at(trigger.id)
    except Exception:
        logger.exception("failed to register trigger=%s", trigger.id)


def _clear_next_run_at(trigger_id: str) -> None:
    with Session(engine) as session:
        trig = session.get(Trigger, trigger_id)
        if trig is None:
            return
        trig.next_run_at = None
        trig.updated_at = _utcnow()
        session.add(trig)
        session.commit()


def _register_poll_trigger(trigger: Trigger) -> None:
    if _scheduler is None:
        return
    job_id = _poll_job_id(trigger.id)
    interval = max(int(trigger.min_poll_interval_s or 60), 10)
    if not trigger.enabled:
        try:
            _scheduler.remove_job(job_id)
        except Exception:
            pass
        return
    try:
        _scheduler.add_job(
            _poll_trigger,
            trigger=IntervalTrigger(seconds=interval),
            id=job_id,
            args=[trigger.id],
            replace_existing=True,
            misfire_grace_time=sched_svc.MISFIRE_GRACE_SECONDS,
        )
        logger.info(
            "registered poll trigger=%s interval=%ds", trigger.id, interval
        )
    except Exception:
        logger.exception("failed to register poll trigger=%s", trigger.id)


def unregister_trigger(trigger_id: str) -> None:
    if _scheduler is None:
        return
    for job_id in (_job_id(trigger_id), _poll_job_id(trigger_id)):
        try:
            _scheduler.remove_job(job_id)
            logger.info("unregistered trigger=%s job=%s", trigger_id, job_id)
        except Exception:
            pass


def _trigger_last_activity(trig: Trigger) -> datetime:
    for ts in (trig.last_fired_at, trig.last_polled_at, trig.updated_at, trig.created_at):
        if ts is not None:
            return ts
    return trig.created_at


def select_triggers_for_boot(rows: list[Trigger]) -> list[Trigger]:
    """Skip stale dormant triggers and cap registration volume at startup."""
    if not rows:
        return []
    max_total = max(int(settings.trigger_max_active), 0)
    max_poll_per_wf = max(int(settings.trigger_max_poll_per_workflow), 0)
    stale_days = max(int(settings.trigger_stale_days), 0)
    cutoff = _utcnow() - timedelta(days=stale_days)

    eligible: list[Trigger] = []
    for trig in sorted(rows, key=_trigger_last_activity, reverse=True):
        never_ran = trig.last_fired_at is None and trig.last_polled_at is None
        created_at = trig.created_at
        if created_at is not None and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if stale_days > 0 and never_ran and created_at is not None and created_at < cutoff:
            continue
        eligible.append(trig)

    poll_per_wf: dict[str, int] = {}
    selected: list[Trigger] = []
    for trig in eligible:
        if max_total > 0 and len(selected) >= max_total:
            break
        if trig.type == "poll" and max_poll_per_wf > 0:
            count = poll_per_wf.get(trig.workflow_id, 0)
            if count >= max_poll_per_wf:
                continue
            poll_per_wf[trig.workflow_id] = count + 1
        selected.append(trig)

    skipped = len(rows) - len(selected)
    if skipped:
        logger.warning(
            "trigger hygiene: registered %d/%d enabled triggers "
            "(max_active=%d, stale_days=%d, max_poll_per_workflow=%d)",
            len(selected),
            len(rows),
            max_total,
            stale_days,
            max_poll_per_wf,
        )
    return selected


def list_jobs() -> list[dict]:
    if _scheduler is None:
        return []
    out: list[dict] = []
    for job in _scheduler.get_jobs():
        nrt = _job_next_run_time(job)
        out.append({
            "id": job.id,
            "next_run_time": nrt.isoformat() if nrt else None,
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
        cron_rows = session.exec(
            select(Trigger).where(
                Trigger.type == "cron", Trigger.enabled.is_(True)  # type: ignore[attr-defined]
            )
        ).all()
        poll_rows = session.exec(
            select(Trigger).where(
                Trigger.type == "poll", Trigger.enabled.is_(True)  # type: ignore[attr-defined]
            )
        ).all()
    cron_rows = select_triggers_for_boot(cron_rows)
    poll_rows = select_triggers_for_boot(poll_rows)
    count = 0
    for trig in cron_rows:
        try:
            register_trigger(trig)
            count += 1
        except Exception:
            logger.exception("failed to register trigger=%s on boot", trig.id)
    poll_count = 0
    for trig in poll_rows:
        try:
            register_trigger(trig)
            poll_count += 1
        except Exception:
            logger.exception("failed to register poll trigger=%s on boot", trig.id)
    _scheduler.start()
    logger.info(
        "scheduler started with %d cron jobs and %d poll jobs", count, poll_count
    )


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
    "refresh_next_run_at",
    "register_trigger",
    "unregister_trigger",
    "get_scheduler",
    "list_jobs",
    "select_triggers_for_boot",
]
