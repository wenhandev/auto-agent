"""CRUD for workflow triggers, plus the public webhook fire endpoint."""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Optional

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlmodel import Session, select

from app.db.crypto import decrypt, encrypt
from app.db.models import Trigger, Workflow
from app.db.session import get_session
from app.schemas_api import (
    TriggerCreate,
    TriggerOut,
    TriggerUpdate,
    WebhookFireResponse,
)
from app.services import runs as run_svc
from app.services import scheduler as scheduler_svc


logger = logging.getLogger(__name__)

router = APIRouter(tags=["triggers"])


_WEBHOOK_PATH_RE = re.compile(r"^[a-z0-9-]{3,64}$")
_BODY_CAP_BYTES = 64 * 1024


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _mask_secret(plain: str) -> str:
    if not plain:
        return ""
    if len(plain) <= 6:
        return "***" + plain[-2:]
    return plain[:4] + "***" + plain[-3:]


def _build_webhook_url(request: Optional[Request], path: str) -> str:
    if request is not None:
        try:
            return str(request.url_for("trigger_webhook_fire", path=path))
        except Exception:
            pass
    return f"http://localhost:8001/api/triggers/webhook/{path}"


def _trigger_to_out(
    trig: Trigger,
    request: Optional[Request] = None,
    *,
    secret_full: Optional[str] = None,
) -> TriggerOut:
    webhook_url: Optional[str] = None
    secret_masked: Optional[str] = None
    if trig.type == "webhook":
        webhook_url = _build_webhook_url(request, trig.schedule_or_path)
        if trig.secret_ciphertext is not None:
            try:
                plain = decrypt(trig.secret_ciphertext).decode("utf-8")
                secret_masked = _mask_secret(plain)
            except Exception:
                logger.exception("decrypt webhook secret failed trigger=%s", trig.id)
                secret_masked = "***"
    return TriggerOut(
        id=trig.id,
        workflow_id=trig.workflow_id,
        type=trig.type,  # type: ignore[arg-type]
        schedule_or_path=trig.schedule_or_path,
        enabled=trig.enabled,
        auth_mode=trig.auth_mode,  # type: ignore[arg-type]
        last_fired_at=trig.last_fired_at,
        created_at=trig.created_at,
        updated_at=trig.updated_at,
        webhook_url=webhook_url,
        secret_masked=secret_masked,
        secret_full=secret_full,
    )


def _generate_webhook_path() -> str:
    raw = secrets.token_urlsafe(8).lower()
    cleaned = re.sub(r"[^a-z0-9]", "-", raw).strip("-")
    if len(cleaned) < 3:
        cleaned = (cleaned + "abc")[:3]
    return cleaned[:64]


def _generate_secret() -> str:
    return secrets.token_urlsafe(32)


def _validate_cron(expr: str) -> Optional[str]:
    try:
        CronTrigger.from_crontab(expr)
        return None
    except Exception as exc:
        return str(exc)


@router.get(
    "/api/workflows/{workflow_id}/triggers",
    response_model=list[TriggerOut],
)
def list_triggers(
    workflow_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> list[TriggerOut]:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow not found")
    rows = session.exec(
        select(Trigger)
        .where(Trigger.workflow_id == workflow_id)
        .order_by(Trigger.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [_trigger_to_out(t, request) for t in rows]


@router.post(
    "/api/workflows/{workflow_id}/triggers",
    response_model=TriggerOut,
)
def create_trigger(
    workflow_id: str,
    body: TriggerCreate,
    request: Request,
    session: Session = Depends(get_session),
) -> TriggerOut:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow not found")

    if body.type not in ("cron", "webhook", "manual"):
        raise HTTPException(422, detail="type must be one of cron|webhook|manual")

    schedule_or_path = (body.schedule_or_path or "").strip()
    secret_full: Optional[str] = None
    secret_ciphertext: Optional[bytes] = None

    if body.type == "cron":
        if not schedule_or_path:
            raise HTTPException(422, detail="cron trigger requires schedule_or_path")
        err = _validate_cron(schedule_or_path)
        if err is not None:
            raise HTTPException(422, detail=f"invalid cron expression: {err}")
    elif body.type == "webhook":
        if not schedule_or_path:
            schedule_or_path = _generate_webhook_path()
        if not _WEBHOOK_PATH_RE.match(schedule_or_path):
            raise HTTPException(
                422,
                detail="webhook path must match [a-z0-9-]{3,64}",
            )
        existing = session.exec(
            select(Trigger).where(
                Trigger.type == "webhook",
                Trigger.schedule_or_path == schedule_or_path,
            )
        ).first()
        if existing is not None:
            raise HTTPException(409, detail="webhook path already in use")
        secret_full = _generate_secret()
        secret_ciphertext = encrypt(secret_full.encode("utf-8"))
    else:
        if not schedule_or_path:
            schedule_or_path = "manual"

    trig = Trigger(
        workflow_id=workflow_id,
        type=body.type,
        schedule_or_path=schedule_or_path,
        enabled=body.enabled,
        secret_ciphertext=secret_ciphertext,
        auth_mode="query_secret",
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    session.add(trig)
    session.commit()
    session.refresh(trig)

    if trig.type == "cron" and trig.enabled:
        scheduler_svc.register_trigger(trig)

    return _trigger_to_out(trig, request, secret_full=secret_full)


@router.patch("/api/triggers/{trigger_id}", response_model=TriggerOut)
def update_trigger(
    trigger_id: str,
    body: TriggerUpdate,
    request: Request,
    session: Session = Depends(get_session),
) -> TriggerOut:
    trig = session.get(Trigger, trigger_id)
    if trig is None:
        raise HTTPException(404, detail="trigger not found")

    secret_full: Optional[str] = None

    if body.schedule_or_path is not None:
        new_path = body.schedule_or_path.strip()
        if trig.type == "cron":
            err = _validate_cron(new_path)
            if err is not None:
                raise HTTPException(422, detail=f"invalid cron expression: {err}")
        elif trig.type == "webhook":
            if not _WEBHOOK_PATH_RE.match(new_path):
                raise HTTPException(
                    422, detail="webhook path must match [a-z0-9-]{3,64}"
                )
            collision = session.exec(
                select(Trigger).where(
                    Trigger.type == "webhook",
                    Trigger.schedule_or_path == new_path,
                    Trigger.id != trig.id,
                )
            ).first()
            if collision is not None:
                raise HTTPException(409, detail="webhook path already in use")
        trig.schedule_or_path = new_path

    if body.enabled is not None:
        trig.enabled = body.enabled

    if body.regenerate_secret:
        if trig.type != "webhook":
            raise HTTPException(
                400, detail="regenerate_secret only valid for webhook triggers"
            )
        secret_full = _generate_secret()
        trig.secret_ciphertext = encrypt(secret_full.encode("utf-8"))

    trig.updated_at = _utcnow()
    session.add(trig)
    session.commit()
    session.refresh(trig)

    if trig.type == "cron":
        scheduler_svc.unregister_trigger(trig.id)
        if trig.enabled:
            scheduler_svc.register_trigger(trig)

    return _trigger_to_out(trig, request, secret_full=secret_full)


@router.delete("/api/triggers/{trigger_id}")
def delete_trigger(
    trigger_id: str, session: Session = Depends(get_session)
) -> Response:
    trig = session.get(Trigger, trigger_id)
    if trig is None:
        raise HTTPException(404, detail="trigger not found")
    if trig.type == "cron":
        scheduler_svc.unregister_trigger(trig.id)
    session.delete(trig)
    session.commit()
    return Response(status_code=204)


@router.post(
    "/api/triggers/webhook/{path}",
    response_model=WebhookFireResponse,
    name="trigger_webhook_fire",
)
async def fire_webhook(
    path: str,
    request: Request,
    secret: str = Query(default=""),
    session: Session = Depends(get_session),
) -> WebhookFireResponse:
    trig = session.exec(
        select(Trigger).where(
            Trigger.type == "webhook",
            Trigger.schedule_or_path == path,
            Trigger.enabled.is_(True),  # type: ignore[attr-defined]
        )
    ).first()
    if trig is None:
        raise HTTPException(404, detail="webhook not found")

    if trig.auth_mode != "query_secret":
        raise HTTPException(
            400, detail="unsupported auth_mode for this endpoint"
        )

    if trig.secret_ciphertext is None:
        raise HTTPException(401, detail="invalid secret")

    try:
        stored_plain = decrypt(trig.secret_ciphertext).decode("utf-8")
    except Exception:
        logger.exception("decrypt webhook secret failed trigger=%s", trig.id)
        raise HTTPException(500, detail="server secret unreadable")

    if not secrets.compare_digest(stored_plain, secret or ""):
        raise HTTPException(401, detail="invalid secret")

    raw = await request.body()
    truncated = False
    if len(raw) > _BODY_CAP_BYTES:
        raw = raw[:_BODY_CAP_BYTES]
        truncated = True
    parsed_body: Optional[dict] = None
    if raw:
        try:
            parsed_body = json.loads(raw)
            if not isinstance(parsed_body, dict):
                parsed_body = {"_raw": parsed_body}
        except Exception:
            parsed_body = {"_raw_text": raw.decode("utf-8", errors="replace")}

    client_ip: Optional[str] = None
    if request.client is not None:
        client_ip = request.client.host

    ctx: dict = {
        "kind": "webhook",
        "trigger_id": trig.id,
        "body": parsed_body,
        "ip": client_ip,
    }
    if truncated:
        ctx["truncated"] = True

    trig.last_fired_at = _utcnow()
    trig.updated_at = _utcnow()
    session.add(trig)
    session.commit()

    try:
        run = run_svc.enqueue_run(
            trig.workflow_id,
            session,
            source="webhook",
            trigger_id=trig.id,
            trigger_context=ctx,
        )
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))

    return WebhookFireResponse(run_id=run.id, status="queued")


@router.get("/api/scheduler/_debug/jobs")
def debug_scheduler_jobs() -> dict:
    if os.environ.get("AUTO_AGENT_DEBUG") != "1":
        raise HTTPException(404, detail="not found")
    return {"jobs": scheduler_svc.list_jobs()}


__all__ = ["router"]
