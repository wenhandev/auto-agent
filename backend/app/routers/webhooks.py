"""CRUD for outbound webhook subscriptions and delivery management."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlmodel import Session, select

from app.auth.api_key import require_api_key
from app.db.crypto import decrypt
from app.db.models import WebhookDelivery, WebhookSubscription, Workflow
from app.db.session import get_session
from app.nodes._http_client import SSRFError as SSRFValidationError
from app.schemas_api import (
    WebhookDeliveryOut,
    WebhookReplayResponse,
    WebhookSubscriptionCreate,
    WebhookSubscriptionOut,
    WebhookSubscriptionUpdate,
    WebhookTestResponse,
)
from app.services import webhooks as webhook_svc


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/webhooks",
    tags=["webhooks"],
    dependencies=[Depends(require_api_key)],
)
internal_router = APIRouter(prefix="/api/internal/webhooks", tags=["webhooks-internal"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _mask_secret(plain: str) -> str:
    if not plain:
        return ""
    if len(plain) <= 6:
        return "***" + plain[-2:]
    return plain[:4] + "***" + plain[-3:]


def _subscription_to_out(sub: WebhookSubscription) -> WebhookSubscriptionOut:
    try:
        plain = decrypt(sub.secret_ciphertext).decode("utf-8")
        masked = _mask_secret(plain)
    except Exception:
        logger.exception("decrypt webhook subscription secret failed id=%s", sub.id)
        masked = "***"
    return WebhookSubscriptionOut(
        id=sub.id,
        url=sub.url,
        events=sub.events or [],
        enabled=sub.enabled,
        workflow_id=sub.workflow_id,
        secret_masked=masked,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )


def _delivery_to_out(row: WebhookDelivery) -> WebhookDeliveryOut:
    try:
        payload = json.loads(row.payload_json)
        if not isinstance(payload, dict):
            payload = {"_raw": payload}
    except Exception:
        payload = {}
    return WebhookDeliveryOut(
        id=row.id,
        subscription_id=row.subscription_id,
        event=row.event,
        attempt=row.attempt,
        status=row.status,  # type: ignore[arg-type]
        response_code=row.response_code,
        next_attempt_at=row.next_attempt_at,
        signature=row.signature,
        payload=payload,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _validate_workflow(session: Session, workflow_id: Optional[str]) -> None:
    if workflow_id is None:
        return
    if session.get(Workflow, workflow_id) is None:
        raise HTTPException(404, detail=f"workflow {workflow_id!r} not found")


def list_subscriptions(session: Session = Depends(get_session)) -> list[WebhookSubscriptionOut]:
    rows = session.exec(select(WebhookSubscription)).all()
    return [_subscription_to_out(r) for r in rows]


def create_subscription(
    body: WebhookSubscriptionCreate,
    session: Session = Depends(get_session),
) -> WebhookSubscriptionOut:
    try:
        webhook_svc.validate_target_url(body.url)
    except SSRFValidationError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    _validate_workflow(session, body.workflow_id)
    secret = body.secret or webhook_svc.generate_secret()
    sub = WebhookSubscription(
        url=body.url.strip(),
        events=list(body.events),
        secret_ciphertext=webhook_svc.encrypt_secret(secret),
        enabled=body.enabled,
        workflow_id=body.workflow_id,
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return _subscription_to_out(sub)


def get_subscription(
    subscription_id: str,
    session: Session = Depends(get_session),
) -> WebhookSubscriptionOut:
    sub = session.get(WebhookSubscription, subscription_id)
    if sub is None:
        raise HTTPException(404, detail="subscription not found")
    return _subscription_to_out(sub)


def update_subscription(
    subscription_id: str,
    body: WebhookSubscriptionUpdate,
    session: Session = Depends(get_session),
) -> WebhookSubscriptionOut:
    sub = session.get(WebhookSubscription, subscription_id)
    if sub is None:
        raise HTTPException(404, detail="subscription not found")
    if body.url is not None:
        try:
            webhook_svc.validate_target_url(body.url)
        except SSRFValidationError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        sub.url = body.url.strip()
    if body.events is not None:
        sub.events = list(body.events)
    if body.secret is not None:
        sub.secret_ciphertext = webhook_svc.encrypt_secret(body.secret)
    if body.enabled is not None:
        sub.enabled = body.enabled
    if body.workflow_id is not None:
        _validate_workflow(session, body.workflow_id)
        sub.workflow_id = body.workflow_id
    sub.updated_at = _utcnow()
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return _subscription_to_out(sub)


def delete_subscription(
    subscription_id: str,
    session: Session = Depends(get_session),
) -> Response:
    sub = session.get(WebhookSubscription, subscription_id)
    if sub is None:
        raise HTTPException(404, detail="subscription not found")
    session.delete(sub)
    session.commit()
    return Response(status_code=204)


def test_subscription(
    subscription_id: str,
    session: Session = Depends(get_session),
) -> WebhookTestResponse:
    if session.get(WebhookSubscription, subscription_id) is None:
        raise HTTPException(404, detail="subscription not found")
    try:
        delivery = webhook_svc.send_test_event(subscription_id)
    except SSRFValidationError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    return WebhookTestResponse(delivery_id=delivery.id)


def list_deliveries(
    subscription_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[WebhookDeliveryOut]:
    stmt = select(WebhookDelivery)
    if subscription_id:
        stmt = stmt.where(WebhookDelivery.subscription_id == subscription_id)
    if status:
        stmt = stmt.where(WebhookDelivery.status == status)
    stmt = stmt.order_by(WebhookDelivery.created_at.desc())  # type: ignore[attr-defined]
    rows = session.exec(stmt).all()
    return [_delivery_to_out(r) for r in rows[:limit]]


def replay_delivery(delivery_id: str) -> WebhookReplayResponse:
    try:
        webhook_svc.replay_delivery(delivery_id)
    except ValueError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    return WebhookReplayResponse(delivery_id=delivery_id)


def _register_routes(target: APIRouter) -> None:
    target.get("", response_model=list[WebhookSubscriptionOut])(list_subscriptions)
    target.post("", response_model=WebhookSubscriptionOut, status_code=201)(create_subscription)
    target.get("/deliveries", response_model=list[WebhookDeliveryOut])(list_deliveries)
    target.post("/deliveries/{delivery_id}/replay", response_model=WebhookReplayResponse)(
        replay_delivery
    )
    target.get("/{subscription_id}", response_model=WebhookSubscriptionOut)(get_subscription)
    target.patch("/{subscription_id}", response_model=WebhookSubscriptionOut)(update_subscription)
    target.delete("/{subscription_id}", status_code=204, response_class=Response)(delete_subscription)
    target.post("/{subscription_id}/test", response_model=WebhookTestResponse)(test_subscription)


_register_routes(router)
_register_routes(internal_router)

__all__ = ["router", "internal_router"]
