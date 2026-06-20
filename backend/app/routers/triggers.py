"""CRUD for workflow triggers, plus public webhook and app callback endpoints."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Coroutine, Optional, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlmodel import Session, select

from app.auth.context import AuthContext, get_org_context, require_org_match
from app.db.crypto import decrypt, encrypt
from app.db.models import Trigger, Workflow, WorkflowVersion
from app.db.session import get_session
from app.integrations.json_path import resolve_path
from app.integrations.registry import resolve_trigger_descriptor
from app.schemas_api import (
    AppTriggerFireResponse,
    NextFiresResponse,
    TriggerCreate,
    TriggerOut,
    TriggerUpdate,
    WebhookFireResponse,
)
from app.services import app_subscriptions as app_sub_svc
from app.services import processed_events as dedup_svc
from app.services import runs as run_svc
from app.services import scheduler as scheduler_svc
from app.services import trigger_scheduling as sched_svc
from app.services import workflow_parameters as param_svc
from app.services import workflows as workflow_svc
from app.services.app_webhook_verify import (
    WebhookVerificationError,
    challenge_response,
    extract_event_id,
    verify_event,
)
from app.services.webhook_signing import SIGNATURE_HEADER, verify_signature


logger = logging.getLogger(__name__)

router = APIRouter(tags=["triggers"])

T = TypeVar("T")

_WEBHOOK_PATH_RE = re.compile(r"^[a-z0-9-]{3,64}$")
_BODY_CAP_BYTES = 64 * 1024


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _run_async(coro: Coroutine[Any, Any, T]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("sync trigger endpoint called from async context")


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


def _trigger_parameters_out(trig: Trigger) -> Optional[dict[str, Any]]:
    raw = getattr(trig, "parameters_json", None)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _trigger_to_out(
    trig: Trigger,
    request: Optional[Request] = None,
    *,
    secret_full: Optional[str] = None,
) -> TriggerOut:
    webhook_url: Optional[str] = None
    secret_masked: Optional[str] = None
    app_callback_url: Optional[str] = None
    subscription_status: Optional[str] = None

    if trig.type == "webhook":
        webhook_url = _build_webhook_url(request, trig.schedule_or_path)
        if trig.secret_ciphertext is not None:
            try:
                plain = decrypt(trig.secret_ciphertext).decode("utf-8")
                secret_masked = _mask_secret(plain)
            except Exception:
                logger.exception("decrypt webhook secret failed trigger=%s", trig.id)
                secret_masked = "***"
    elif trig.type == "app":
        app_callback_url = app_sub_svc.build_app_callback_url(request, trig.id)
        subscription_status = "active" if trig.subscription_id else "inactive"

    return TriggerOut(
        id=trig.id,
        workflow_id=trig.workflow_id,
        type=trig.type,  # type: ignore[arg-type]
        schedule_or_path=trig.schedule_or_path,
        enabled=trig.enabled,
        timezone=getattr(trig, "timezone", None) or sched_svc.DEFAULT_TIMEZONE,
        misfire_policy=getattr(trig, "misfire_policy", None) or "skip",  # type: ignore[arg-type]
        next_run_at=getattr(trig, "next_run_at", None),
        auth_mode=trig.auth_mode,  # type: ignore[arg-type]
        last_fired_at=trig.last_fired_at,
        created_at=trig.created_at,
        updated_at=trig.updated_at,
        webhook_url=webhook_url,
        secret_masked=secret_masked,
        secret_full=secret_full,
        poll_app=trig.poll_app,
        poll_resource=trig.poll_resource,
        poll_operation=trig.poll_operation,
        poll_credential=trig.poll_credential,
        poll_dedup_path=trig.poll_dedup_path,
        poll_mode=trig.poll_mode,  # type: ignore[arg-type]
        on_first_poll=trig.on_first_poll,  # type: ignore[arg-type]
        min_poll_interval_s=trig.min_poll_interval_s,
        last_polled_at=trig.last_polled_at,
        app_name=trig.app_name,
        app_trigger=trig.app_trigger,
        app_credential=trig.app_credential,
        subscription_id=trig.subscription_id,
        app_callback_url=app_callback_url,
        subscription_status=subscription_status,
        parameters=_trigger_parameters_out(trig),
    )


def _generate_webhook_path() -> str:
    raw = secrets.token_urlsafe(8).lower()
    cleaned = re.sub(r"[^a-z0-9]", "-", raw).strip("-")
    if len(cleaned) < 3:
        cleaned = (cleaned + "abc")[:3]
    return cleaned[:64]


def _generate_secret() -> str:
    return secrets.token_urlsafe(32)


def _workflow_for_org(
    session: Session, workflow_id: str, org_id: str
) -> Workflow:
    workflow = session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="workflow not found")
    require_org_match(workflow.org_id, org_id, session)
    return workflow


def _trigger_for_org(
    session: Session, trigger_id: str, org_id: str
) -> Trigger:
    trig = session.get(Trigger, trigger_id)
    if trig is None:
        raise HTTPException(404, detail="trigger not found")
    workflow = session.get(Workflow, trig.workflow_id)
    if workflow is None:
        raise HTTPException(404, detail="trigger not found")
    require_org_match(workflow.org_id, org_id, session)
    return trig


def _trigger_for_workflow_org(
    session: Session, workflow_id: str, trigger_id: str, org_id: str
) -> Trigger:
    _workflow_for_org(session, workflow_id, org_id)
    trig = session.get(Trigger, trigger_id)
    if trig is None or trig.workflow_id != workflow_id:
        raise HTTPException(404, detail="trigger not found")
    return trig


def _validate_cron(expr: str, timezone: str) -> Optional[str]:
    return sched_svc.validate_cron(expr, timezone)


def _validate_timezone(tz: str) -> Optional[str]:
    return sched_svc.validate_timezone(tz)


def _validate_misfire_policy(policy: str) -> Optional[str]:
    if policy not in ("skip", "catch_up"):
        return "misfire_policy must be skip or catch_up"
    return None


def _reconcile_trigger(trig: Trigger, *, was_enabled: bool) -> None:
    if trig.type in ("cron", "poll"):
        scheduler_svc.unregister_trigger(trig.id)
        if trig.enabled:
            scheduler_svc.register_trigger(trig)
        if trig.type == "cron":
            scheduler_svc.refresh_next_run_at(trig.id)
    elif trig.type == "app":
        if trig.enabled and not was_enabled:
            _run_async(app_sub_svc.enable_app_trigger(trig))
        elif not trig.enabled and was_enabled:
            _run_async(app_sub_svc.disable_app_trigger(trig))


@router.get(
    "/api/workflows/{workflow_id}/triggers",
    response_model=list[TriggerOut],
)
def list_triggers(
    workflow_id: str,
    request: Request,
    session: Session = Depends(get_session),
    _ctx: AuthContext = Depends(get_org_context),
) -> list[TriggerOut]:
    _workflow_for_org(session, workflow_id, _ctx.org_id)
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
    _ctx: AuthContext = Depends(get_org_context),
) -> TriggerOut:
    _workflow_for_org(session, workflow_id, _ctx.org_id)

    timezone = body.timezone or sched_svc.DEFAULT_TIMEZONE
    tz_err = _validate_timezone(timezone)
    if tz_err is not None:
        raise HTTPException(422, detail=tz_err)
    policy_err = _validate_misfire_policy(body.misfire_policy)
    if policy_err is not None:
        raise HTTPException(422, detail=policy_err)

    if body.type not in ("cron", "webhook", "manual", "poll", "app"):
        raise HTTPException(
            422, detail="type must be one of cron|webhook|manual|poll|app"
        )

    schedule_or_path = (body.schedule_or_path or "").strip()
    secret_full: Optional[str] = None
    secret_ciphertext: Optional[bytes] = None

    poll_fields: dict[str, Any] = {}
    app_fields: dict[str, Any] = {}

    if body.type == "cron":
        if not schedule_or_path:
            raise HTTPException(422, detail="cron trigger requires schedule_or_path")
        err = _validate_cron(schedule_or_path, timezone)
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
    elif body.type == "poll":
        if not body.poll_app or not body.poll_resource or not body.poll_operation:
            raise HTTPException(
                422, detail="poll trigger requires poll_app, poll_resource, poll_operation"
            )
        if not body.poll_credential:
            raise HTTPException(422, detail="poll trigger requires poll_credential")
        if not schedule_or_path:
            schedule_or_path = "poll"
        poll_fields = {
            "poll_app": body.poll_app,
            "poll_resource": body.poll_resource,
            "poll_operation": body.poll_operation,
            "poll_credential": body.poll_credential,
            "poll_dedup_path": body.poll_dedup_path or "id",
            "poll_mode": body.poll_mode,
            "on_first_poll": body.on_first_poll,
            "min_poll_interval_s": body.min_poll_interval_s,
        }
    elif body.type == "app":
        if not body.app_name or not body.app_trigger:
            raise HTTPException(
                422, detail="app trigger requires app_name and app_trigger"
            )
        if not body.app_credential:
            raise HTTPException(422, detail="app trigger requires app_credential")
        try:
            resolve_trigger_descriptor(body.app_name, body.app_trigger)
        except KeyError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        if not schedule_or_path:
            schedule_or_path = body.app_trigger
        app_fields = {
            "app_name": body.app_name,
            "app_trigger": body.app_trigger,
            "app_credential": body.app_credential,
        }
    else:
        if not schedule_or_path:
            schedule_or_path = "manual"

    parameters_json: Optional[str] = None
    if body.parameters is not None:
        parameters_json = json.dumps(body.parameters, ensure_ascii=False, default=str)

    trig = Trigger(
        workflow_id=workflow_id,
        type=body.type,
        schedule_or_path=schedule_or_path,
        enabled=body.enabled,
        timezone=timezone,
        misfire_policy=body.misfire_policy,
        secret_ciphertext=secret_ciphertext,
        auth_mode=body.auth_mode if body.type == "webhook" else "query_secret",
        parameters_json=parameters_json,
        created_at=_utcnow(),
        updated_at=_utcnow(),
        **poll_fields,
        **app_fields,
    )
    session.add(trig)
    session.commit()
    session.refresh(trig)

    if trig.enabled:
        if trig.type in ("cron", "poll"):
            scheduler_svc.register_trigger(trig)
        elif trig.type == "app":
            _run_async(app_sub_svc.enable_app_trigger(trig, request=request))
            session.refresh(trig)
        if trig.type == "cron":
            scheduler_svc.refresh_next_run_at(trig.id)
            session.refresh(trig)

    return _trigger_to_out(trig, request, secret_full=secret_full)


def _apply_trigger_update(
    trig: Trigger,
    body: TriggerUpdate,
    session: Session,
    *,
    was_enabled: bool,
) -> tuple[Trigger, Optional[str]]:
    secret_full: Optional[str] = None
    tz = getattr(trig, "timezone", None) or sched_svc.DEFAULT_TIMEZONE

    if body.timezone is not None:
        tz_err = _validate_timezone(body.timezone)
        if tz_err is not None:
            raise HTTPException(422, detail=tz_err)
        trig.timezone = body.timezone
        tz = body.timezone

    if body.misfire_policy is not None:
        policy_err = _validate_misfire_policy(body.misfire_policy)
        if policy_err is not None:
            raise HTTPException(422, detail=policy_err)
        trig.misfire_policy = body.misfire_policy

    if body.schedule_or_path is not None:
        new_path = body.schedule_or_path.strip()
        if trig.type == "cron":
            err = _validate_cron(new_path, tz)
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

    if body.auth_mode is not None:
        if trig.type != "webhook":
            raise HTTPException(400, detail="auth_mode only valid for webhook triggers")
        trig.auth_mode = body.auth_mode

    if body.regenerate_secret:
        if trig.type != "webhook":
            raise HTTPException(
                400, detail="regenerate_secret only valid for webhook triggers"
            )
        secret_full = _generate_secret()
        trig.secret_ciphertext = encrypt(secret_full.encode("utf-8"))

    if body.poll_dedup_path is not None:
        trig.poll_dedup_path = body.poll_dedup_path
    if body.poll_mode is not None:
        trig.poll_mode = body.poll_mode
    if body.on_first_poll is not None:
        trig.on_first_poll = body.on_first_poll
    if body.min_poll_interval_s is not None:
        trig.min_poll_interval_s = body.min_poll_interval_s
    if body.parameters is not None:
        trig.parameters_json = json.dumps(
            body.parameters, ensure_ascii=False, default=str
        )

    trig.updated_at = _utcnow()
    session.add(trig)
    session.commit()
    session.refresh(trig)

    _reconcile_trigger(trig, was_enabled=was_enabled)
    session.refresh(trig)
    return trig, secret_full


@router.patch("/api/triggers/{trigger_id}", response_model=TriggerOut)
def update_trigger(
    trigger_id: str,
    body: TriggerUpdate,
    request: Request,
    session: Session = Depends(get_session),
    _ctx: AuthContext = Depends(get_org_context),
) -> TriggerOut:
    trig = _trigger_for_org(session, trigger_id, _ctx.org_id)
    was_enabled = trig.enabled
    trig, secret_full = _apply_trigger_update(
        trig, body, session, was_enabled=was_enabled
    )
    return _trigger_to_out(trig, request, secret_full=secret_full)


@router.put(
    "/api/workflows/{workflow_id}/triggers/{trigger_id}",
    response_model=TriggerOut,
)
def update_workflow_trigger(
    workflow_id: str,
    trigger_id: str,
    body: TriggerUpdate,
    request: Request,
    session: Session = Depends(get_session),
    _ctx: AuthContext = Depends(get_org_context),
) -> TriggerOut:
    trig = _trigger_for_workflow_org(
        session, workflow_id, trigger_id, _ctx.org_id
    )
    was_enabled = trig.enabled
    trig, secret_full = _apply_trigger_update(
        trig, body, session, was_enabled=was_enabled
    )
    return _trigger_to_out(trig, request, secret_full=secret_full)


@router.post(
    "/api/workflows/{workflow_id}/triggers/{trigger_id}/regenerate-secret",
    response_model=TriggerOut,
)
def regenerate_trigger_secret(
    workflow_id: str,
    trigger_id: str,
    request: Request,
    session: Session = Depends(get_session),
    _ctx: AuthContext = Depends(get_org_context),
) -> TriggerOut:
    trig = _trigger_for_workflow_org(
        session, workflow_id, trigger_id, _ctx.org_id
    )
    if trig.type != "webhook":
        raise HTTPException(400, detail="regenerate-secret only valid for webhook triggers")
    was_enabled = trig.enabled
    body = TriggerUpdate(regenerate_secret=True)
    trig, secret_full = _apply_trigger_update(
        trig, body, session, was_enabled=was_enabled
    )
    return _trigger_to_out(trig, request, secret_full=secret_full)


@router.get(
    "/api/triggers/{trigger_id}/next-fires",
    response_model=NextFiresResponse,
)
def preview_next_fires(
    trigger_id: str,
    n: int = Query(default=3, ge=1, le=10),
    session: Session = Depends(get_session),
    _ctx: AuthContext = Depends(get_org_context),
) -> NextFiresResponse:
    trig = _trigger_for_org(session, trigger_id, _ctx.org_id)
    if trig.type != "cron":
        raise HTTPException(400, detail="next-fires preview only valid for cron triggers")
    tz = getattr(trig, "timezone", None) or sched_svc.DEFAULT_TIMEZONE
    fires = sched_svc.compute_next_fires(trig.schedule_or_path, tz, n=n)
    return NextFiresResponse(trigger_id=trig.id, timezone=tz, fires=fires)


@router.delete("/api/workflows/{workflow_id}/triggers/{trigger_id}")
def delete_workflow_trigger(
    workflow_id: str,
    trigger_id: str,
    session: Session = Depends(get_session),
    _ctx: AuthContext = Depends(get_org_context),
) -> Response:
    trig = _trigger_for_workflow_org(
        session, workflow_id, trigger_id, _ctx.org_id
    )
    if trig.type in ("cron", "poll"):
        scheduler_svc.unregister_trigger(trig.id)
    elif trig.type == "app" and trig.subscription_id:
        _run_async(app_sub_svc.disable_app_trigger(trig))
    session.delete(trig)
    session.commit()
    return Response(status_code=204)


@router.delete("/api/triggers/{trigger_id}")
def delete_trigger(
    trigger_id: str,
    session: Session = Depends(get_session),
    _ctx: AuthContext = Depends(get_org_context),
) -> Response:
    trig = _trigger_for_org(session, trigger_id, _ctx.org_id)
    if trig.type in ("cron", "poll"):
        scheduler_svc.unregister_trigger(trig.id)
    elif trig.type == "app" and trig.subscription_id:
        _run_async(app_sub_svc.disable_app_trigger(trig))
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

    if trig.secret_ciphertext is None:
        raise HTTPException(401, detail="invalid secret")

    try:
        stored_plain = decrypt(trig.secret_ciphertext).decode("utf-8")
    except Exception:
        logger.exception("decrypt webhook secret failed trigger=%s", trig.id)
        raise HTTPException(500, detail="server secret unreadable")

    raw = await request.body()
    truncated = False
    if len(raw) > _BODY_CAP_BYTES:
        raw = raw[:_BODY_CAP_BYTES]
        truncated = True

    if trig.auth_mode == "query_secret":
        if not secrets.compare_digest(stored_plain, secret or ""):
            raise HTTPException(401, detail="invalid secret")
    elif trig.auth_mode == "hmac":
        sig = request.headers.get(SIGNATURE_HEADER) or request.headers.get(
            SIGNATURE_HEADER.lower()
        )
        if not sig or not verify_signature(raw, stored_plain, sig):
            raise HTTPException(401, detail="invalid signature")
    else:
        raise HTTPException(400, detail="unsupported auth_mode for this endpoint")
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

    mapped_params: Optional[dict[str, Any]] = None
    passthrough: dict[str, Any] = {}
    workflow = session.get(Workflow, trig.workflow_id)
    if workflow is not None and workflow.current_version_id is not None:
        version = session.get(WorkflowVersion, workflow.current_version_id)
        if version is not None:
            try:
                schema = workflow_svc.load_workflow_schema(version)
                body_dict = parsed_body if isinstance(parsed_body, dict) else {}
                mapped_params, passthrough = param_svc.split_trigger_body(
                    schema.parameters, body_dict
                )
            except Exception:
                logger.exception(
                    "webhook parameter mapping failed trigger=%s", trig.id
                )
    if passthrough:
        ctx["context"] = passthrough

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
            parameters=mapped_params,
        )
    except param_svc.ParameterValidationError as exc:
        raise HTTPException(422, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))

    return WebhookFireResponse(run_id=run.id, status="queued")


def _normalize_event_payload(
    payload: dict[str, Any], event_item_path: Optional[str]
) -> dict[str, Any]:
    if not event_item_path:
        return payload
    try:
        val = resolve_path(payload, event_item_path)
        if isinstance(val, dict):
            return val
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return val[0]
    except ValueError:
        pass
    return payload


@router.post(
    "/api/triggers/app/{trigger_id}",
    response_model=AppTriggerFireResponse,
    name="trigger_app_callback",
)
async def app_trigger_callback(
    trigger_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> AppTriggerFireResponse:
    trig = session.get(Trigger, trigger_id)
    if trig is None or trig.type != "app" or not trig.enabled:
        raise HTTPException(404, detail="app trigger not found")

    if not trig.app_name or not trig.app_trigger:
        raise HTTPException(500, detail="app trigger misconfigured")

    _, trig_desc = resolve_trigger_descriptor(trig.app_name, trig.app_trigger)
    spec = trig_desc.verification

    raw = await request.body()
    if len(raw) > _BODY_CAP_BYTES:
        raw = raw[:_BODY_CAP_BYTES]

    payload: dict[str, Any] = {}
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                payload = parsed
            else:
                payload = {"_raw": parsed}
        except Exception:
            payload = {"_raw_text": raw.decode("utf-8", errors="replace")}

    headers = {k: v for k, v in request.headers.items()}

    if spec is not None:
        challenge = challenge_response(payload, spec)
        if challenge is not None:
            field = spec.challenge_response_field or spec.challenge_field or "challenge"
            val = challenge.get(field)
            return AppTriggerFireResponse(status="challenge", challenge=str(val) if val else None)

    secret = app_sub_svc.get_subscription_secret(trig)
    if secret is None:
        raise HTTPException(500, detail="subscription secret unavailable")

    if spec is not None and spec.type in ("hmac", "shared_secret"):
        try:
            event_id = verify_event(
                raw_body=raw,
                headers=headers,
                payload=payload,
                secret=secret,
                spec=spec,
            )
        except WebhookVerificationError as exc:
            raise HTTPException(401, detail=str(exc)) from exc
    else:
        event_id = extract_event_id(payload, spec)

    if dedup_svc.is_processed(trig.id, event_id):
        return AppTriggerFireResponse(status="duplicate")

    context_payload = _normalize_event_payload(payload, trig_desc.event_item_path)
    summary = str(context_payload.get("id") or context_payload.get("type") or "event")

    ctx = {
        "kind": "app",
        "trigger_id": trig.id,
        "event_summary": summary,
        "context": context_payload,
        "headers": headers,
    }

    trig.last_fired_at = _utcnow()
    trig.updated_at = _utcnow()
    session.add(trig)
    session.commit()

    try:
        run = run_svc.enqueue_run(
            trig.workflow_id,
            session,
            source="app",
            trigger_id=trig.id,
            trigger_context=ctx,
        )
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc))

    dedup_svc.mark_processed(trig.id, event_id)
    return AppTriggerFireResponse(run_id=run.id, status="queued")


@router.get("/api/scheduler/_debug/jobs")
def debug_scheduler_jobs() -> dict:
    if os.environ.get("AUTO_AGENT_DEBUG") != "1":
        raise HTTPException(404, detail="not found")
    return {"jobs": scheduler_svc.list_jobs()}


__all__ = ["router"]
