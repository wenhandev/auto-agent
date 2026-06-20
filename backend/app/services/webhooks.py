"""Outbound webhook subscriptions, signing, delivery queue, and retries."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

import httpx
from sqlmodel import Session, select

from app.db.crypto import decrypt, encrypt
from app.db.models import Run, WebhookDelivery, WebhookSubscription
from app.db.session import engine
from app.nodes._http_client import SSRFError, validate_url
from app.services import webhook_signing as signing
from app.settings import settings


logger = logging.getLogger(__name__)

WEBHOOK_EVENTS = frozenset({
    "run_completed",
    "run_failed",
    "run_rejected",
    "run_aborted",
    "approval_requested",
})

_RUN_EVENT_TO_WEBHOOK = {
    "run_completed": "run_completed",
    "run_completed_with_errors": "run_completed",
    "run_failed": "run_failed",
    "run_aborted": "run_aborted",
    "run_rejected": "run_rejected",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _job_id(delivery_id: str) -> str:
    return f"webhook:{delivery_id}"


def validate_target_url(url: str) -> str:
    return validate_url(url)


def _backoff_seconds(attempt: int) -> int:
    schedule = settings.webhook_backoff_schedule or [60, 300, 1800, 7200, 21600]
    idx = min(max(attempt - 1, 0), len(schedule) - 1)
    return int(schedule[idx])


def _serialize_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _decrypt_secret(subscription: WebhookSubscription) -> str:
    return decrypt(subscription.secret_ciphertext).decode("utf-8")


def _build_outputs_summary(extra: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not extra:
        return None
    skip = {"event", "node_id", "ts", "seq", "run_id", "workflow_id", "status"}
    summary = {k: v for k, v in extra.items() if k not in skip}
    return summary or None


def _matching_subscriptions(
    session: Session,
    event: str,
    workflow_id: Optional[str],
) -> list[WebhookSubscription]:
    rows = session.exec(
        select(WebhookSubscription).where(WebhookSubscription.enabled.is_(True))  # type: ignore[attr-defined]
    ).all()
    out: list[WebhookSubscription] = []
    for sub in rows:
        events = sub.events or []
        if event not in events:
            continue
        if sub.workflow_id is not None and sub.workflow_id != workflow_id:
            continue
        out.append(sub)
    return out


def _schedule_delivery(delivery_id: str, run_at: Optional[datetime] = None) -> None:
    from app.services import scheduler as scheduler_svc

    sched = scheduler_svc.get_scheduler()
    if sched is None:
        logger.warning("webhook delivery not scheduled; scheduler not running id=%s", delivery_id)
        return
    when = run_at or _utcnow()
    try:
        sched.add_job(
            _execute_delivery_job,
            trigger="date",
            run_date=when,
            id=_job_id(delivery_id),
            args=[delivery_id],
            replace_existing=True,
            misfire_grace_time=60,
        )
    except Exception:
        logger.exception("failed to schedule webhook delivery id=%s", delivery_id)


def _create_delivery(
    session: Session,
    subscription: WebhookSubscription,
    *,
    event: str,
    payload: dict[str, Any],
    delivery_id: Optional[str] = None,
) -> WebhookDelivery:
    delivery = WebhookDelivery(
        id=delivery_id or str(uuid4()),
        subscription_id=subscription.id,
        event=event,
        payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        attempt=0,
        status="pending",
        next_attempt_at=_utcnow(),
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    session.add(delivery)
    session.commit()
    session.refresh(delivery)
    return delivery


def enqueue_event(
    event: str,
    *,
    run_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    status: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> list[str]:
    if event not in WEBHOOK_EVENTS:
        return []
    payload = {
        "event": event,
        "run_id": run_id,
        "workflow_id": workflow_id,
        "status": status,
        "outputs_summary": _build_outputs_summary(extra),
        "ts": _utcnow().isoformat(),
    }
    delivery_ids: list[str] = []
    with Session(engine) as session:
        subs = _matching_subscriptions(session, event, workflow_id)
        for sub in subs:
            body = {**payload, "delivery_id": None}
            delivery = _create_delivery(session, sub, event=event, payload=body)
            full_payload = {**payload, "delivery_id": delivery.id}
            delivery.payload_json = json.dumps(
                full_payload, ensure_ascii=False, separators=(",", ":")
            )
            delivery.updated_at = _utcnow()
            session.add(delivery)
            session.commit()
            delivery_ids.append(delivery.id)
            _schedule_delivery(delivery.id)
    return delivery_ids


def enqueue_run_terminal(
    run_id: str,
    terminal_event: str,
    *,
    status: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> list[str]:
    webhook_event = _RUN_EVENT_TO_WEBHOOK.get(terminal_event)
    if webhook_event is None:
        return []
    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None:
            return []
        workflow_id = run.workflow_id
        resolved_status = status or run.status
    return enqueue_event(
        webhook_event,
        run_id=run_id,
        workflow_id=workflow_id,
        status=resolved_status,
        extra=extra,
    )


def _execute_delivery_job(delivery_id: str) -> None:
    try:
        import asyncio

        asyncio.get_running_loop()
        asyncio.create_task(execute_delivery(delivery_id))
    except RuntimeError:
        import asyncio

        asyncio.run(execute_delivery(delivery_id))


async def execute_delivery(
    delivery_id: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> WebhookDelivery:
    with Session(engine) as session:
        delivery = session.get(WebhookDelivery, delivery_id)
        if delivery is None:
            raise ValueError(f"delivery {delivery_id!r} not found")
        if delivery.status in ("delivered", "exhausted"):
            return delivery
        subscription = session.get(WebhookSubscription, delivery.subscription_id)
        if subscription is None or not subscription.enabled:
            delivery.status = "exhausted"
            delivery.updated_at = _utcnow()
            session.add(delivery)
            session.commit()
            session.refresh(delivery)
            return delivery

        try:
            validate_target_url(subscription.url)
        except SSRFError as exc:
            delivery.status = "exhausted"
            delivery.response_code = None
            delivery.updated_at = _utcnow()
            session.add(delivery)
            session.commit()
            session.refresh(delivery)
            logger.warning("webhook delivery blocked by SSRF id=%s err=%s", delivery_id, exc)
            return delivery

        secret = _decrypt_secret(subscription)
        body = delivery.payload_json.encode("utf-8")
        signature = signing.sign_body(body, secret)
        target_url = subscription.url
        delivery.attempt += 1
        delivery.signature = signature
        delivery.updated_at = _utcnow()
        session.add(delivery)
        session.commit()

    headers = {
        "Content-Type": "application/json",
        signing.SIGNATURE_HEADER: signature,
        signing.DELIVERY_ID_HEADER: delivery_id,
    }

    response_code: Optional[int] = None
    success = False
    try:
        async with httpx.AsyncClient(transport=transport, timeout=30.0) as client:
            resp = await client.post(target_url, content=body, headers=headers)
        response_code = resp.status_code
        success = 200 <= resp.status_code < 300
    except Exception:
        logger.exception("webhook POST failed delivery=%s url=%s", delivery_id, target_url)

    with Session(engine) as session:
        delivery = session.get(WebhookDelivery, delivery_id)
        if delivery is None:
            raise ValueError(f"delivery {delivery_id!r} not found")
        delivery.response_code = response_code
        delivery.updated_at = _utcnow()
        if success:
            delivery.status = "delivered"
            delivery.next_attempt_at = None
        elif delivery.attempt >= settings.webhook_max_attempts:
            delivery.status = "exhausted"
            delivery.next_attempt_at = None
        else:
            delivery.status = "failed"
            delay = _backoff_seconds(delivery.attempt)
            delivery.next_attempt_at = _utcnow() + timedelta(seconds=delay)
            session.add(delivery)
            session.commit()
            _schedule_delivery(delivery_id, run_at=delivery.next_attempt_at)
            session.refresh(delivery)
            return delivery
        session.add(delivery)
        session.commit()
        session.refresh(delivery)
        return delivery


def replay_delivery(delivery_id: str) -> WebhookDelivery:
    with Session(engine) as session:
        delivery = session.get(WebhookDelivery, delivery_id)
        if delivery is None:
            raise ValueError(f"delivery {delivery_id!r} not found")
        delivery.status = "pending"
        delivery.next_attempt_at = _utcnow()
        delivery.updated_at = _utcnow()
        session.add(delivery)
        session.commit()
        session.refresh(delivery)
    _schedule_delivery(delivery_id)
    return delivery


def send_test_event(subscription_id: str) -> WebhookDelivery:
    with Session(engine) as session:
        sub = session.get(WebhookSubscription, subscription_id)
        if sub is None:
            raise ValueError(f"subscription {subscription_id!r} not found")
        validate_target_url(sub.url)
        event = (sub.events or ["run_completed"])[0]
        payload = {
            "event": event,
            "run_id": None,
            "workflow_id": sub.workflow_id,
            "status": "test",
            "outputs_summary": {"test": True},
            "ts": _utcnow().isoformat(),
        }
        delivery = _create_delivery(session, sub, event=event, payload=payload)
        full_payload = {**payload, "delivery_id": delivery.id}
        delivery.payload_json = json.dumps(
            full_payload, ensure_ascii=False, separators=(",", ":")
        )
        delivery.updated_at = _utcnow()
        session.add(delivery)
        session.commit()
        session.refresh(delivery)
    _schedule_delivery(delivery.id)
    return delivery


def reload_pending_deliveries() -> int:
    now = _utcnow()
    with Session(engine) as session:
        rows = session.exec(
            select(WebhookDelivery).where(
                WebhookDelivery.status.in_(("pending", "failed")),  # type: ignore[attr-defined]
            )
        ).all()
    count = 0
    for row in rows:
        if row.status == "exhausted" or row.status == "delivered":
            continue
        next_at = _as_utc(row.next_attempt_at)
        if next_at is not None and next_at > now:
            _schedule_delivery(row.id, run_at=next_at)
        else:
            _schedule_delivery(row.id)
        count += 1
    logger.info("reloaded %d pending webhook deliveries", count)
    return count


def generate_secret() -> str:
    return uuid4().hex + uuid4().hex[:8]


def encrypt_secret(plain: str) -> bytes:
    return encrypt(plain.encode("utf-8"))


__all__ = [
    "WEBHOOK_EVENTS",
    "enqueue_event",
    "enqueue_run_terminal",
    "execute_delivery",
    "generate_secret",
    "encrypt_secret",
    "reload_pending_deliveries",
    "replay_delivery",
    "send_test_event",
    "validate_target_url",
]
