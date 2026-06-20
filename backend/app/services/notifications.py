from __future__ import annotations

import logging

from app.services import webhooks as webhook_svc


logger = logging.getLogger(__name__)


async def emit(event_name: str, payload: dict) -> None:
    """Fire an event for downstream subscribers (webhooks, email, Slack, …)."""
    logger.info("notifications.emit %s %s", event_name, payload)
    if event_name == "approval_requested":
        webhook_svc.enqueue_event(
            "approval_requested",
            run_id=payload.get("run_id"),
            workflow_id=payload.get("workflow_id"),
            status="approval_requested",
            extra=payload,
        )


__all__ = ["emit"]
