"""App trigger subscription lifecycle (subscribe / unsubscribe)."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import Request
from sqlmodel import Session

from app.db.crypto import decrypt, encrypt
from app.db.models import Trigger
from app.db.session import engine
from app.integrations.json_path import resolve_path
from app.integrations.registry import resolve_operation, resolve_trigger_descriptor
from app.nodes import integration as integration_node

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _generate_secret() -> str:
    return secrets.token_urlsafe(32)


def build_app_callback_url(request: Optional[Request], trigger_id: str) -> str:
    if request is not None:
        try:
            return str(request.url_for("trigger_app_callback", trigger_id=trigger_id))
        except Exception:
            pass
    return f"http://localhost:8001/api/triggers/app/{trigger_id}"


def _subscription_id_from_output(output: dict[str, Any]) -> Optional[str]:
    for path in ("subscription_id", "id", "hook_id"):
        try:
            val = resolve_path(output, path)
            if val:
                return str(val)
        except ValueError:
            continue
    return None


async def subscribe_trigger(
    trigger: Trigger,
    *,
    request: Optional[Request] = None,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> tuple[str, str]:
    """Call provider subscribe op; return (subscription_id, secret_plain)."""
    if not trigger.app_name or not trigger.app_trigger:
        raise ValueError("app trigger missing app_name/app_trigger")
    if not trigger.app_credential:
        raise ValueError("app trigger missing app_credential")

    _, trig_desc = resolve_trigger_descriptor(trigger.app_name, trigger.app_trigger)
    if not trig_desc.subscribe_operation:
        raise ValueError("trigger descriptor missing subscribe_operation")

    desc = resolve_trigger_descriptor(trigger.app_name, trigger.app_trigger)[0]
    resource = trig_desc.resource or (desc.resources[0].name if desc.resources else None)
    if not resource:
        raise ValueError("app trigger missing resource")
    resolve_operation(trigger.app_name, resource, trig_desc.subscribe_operation)

    secret_plain = _generate_secret()
    callback_url = build_app_callback_url(request, trigger.id)

    with Session(engine) as session:
        result = await integration_node.run(
            {
                "app": trigger.app_name,
                "resource": resource,
                "operation": trig_desc.subscribe_operation,
                "credential": trigger.app_credential,
                "fields": {
                    "callback_url": callback_url,
                    "secret": secret_plain,
                },
            },
            input_items=[],
            context={},
            session=session,
            workflow_id=trigger.workflow_id,
            transport=transport,
        )

    sub_id = _subscription_id_from_output(result.output)
    if not sub_id and result.items:
        first = result.items[0].json
        if isinstance(first, dict):
            sub_id = _subscription_id_from_output(first)
    if not sub_id:
        sub_id = secrets.token_urlsafe(12)

    return sub_id, secret_plain


async def unsubscribe_trigger(
    trigger: Trigger,
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> None:
    if not trigger.app_name or not trigger.app_trigger or not trigger.subscription_id:
        return
    _, trig_desc = resolve_trigger_descriptor(trigger.app_name, trigger.app_trigger)
    if not trig_desc.unsubscribe_operation:
        return
    desc = resolve_trigger_descriptor(trigger.app_name, trigger.app_trigger)[0]
    resource = trig_desc.resource or (desc.resources[0].name if desc.resources else None)
    if not resource:
        return

    with Session(engine) as session:
        await integration_node.run(
            {
                "app": trigger.app_name,
                "resource": resource,
                "operation": trig_desc.unsubscribe_operation,
                "credential": trigger.app_credential,
                "fields": {"subscription_id": trigger.subscription_id},
            },
            input_items=[],
            context={},
            session=session,
            workflow_id=trigger.workflow_id,
            transport=transport,
        )


def persist_subscription(
    trigger_id: str,
    subscription_id: str,
    secret_plain: str,
) -> None:
    with Session(engine) as session:
        row = session.get(Trigger, trigger_id)
        if row is None:
            return
        row.subscription_id = subscription_id
        row.subscription_secret_ciphertext = encrypt(secret_plain.encode("utf-8"))
        row.updated_at = _utcnow()
        session.add(row)
        session.commit()


def clear_subscription(trigger_id: str) -> None:
    with Session(engine) as session:
        row = session.get(Trigger, trigger_id)
        if row is None:
            return
        row.subscription_id = None
        row.subscription_secret_ciphertext = None
        row.updated_at = _utcnow()
        session.add(row)
        session.commit()


def get_subscription_secret(trigger: Trigger) -> Optional[str]:
    if trigger.subscription_secret_ciphertext is None:
        return None
    try:
        return decrypt(trigger.subscription_secret_ciphertext).decode("utf-8")
    except Exception:
        logger.exception("decrypt subscription secret failed trigger=%s", trigger.id)
        return None


async def enable_app_trigger(
    trigger: Trigger,
    *,
    request: Optional[Request] = None,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> None:
    sub_id, secret = await subscribe_trigger(
        trigger, request=request, transport=transport
    )
    persist_subscription(trigger.id, sub_id, secret)


async def disable_app_trigger(
    trigger: Trigger,
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> None:
    await unsubscribe_trigger(trigger, transport=transport)
    clear_subscription(trigger.id)


__all__ = [
    "build_app_callback_url",
    "clear_subscription",
    "disable_app_trigger",
    "enable_app_trigger",
    "get_subscription_secret",
    "persist_subscription",
    "subscribe_trigger",
    "unsubscribe_trigger",
]
