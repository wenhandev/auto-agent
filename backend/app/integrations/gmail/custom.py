from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Any

from app.integrations.auth import RenderedRequest


def _build_raw_mime(*, to: str, subject: str, body: str) -> str:
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    return raw.rstrip("=")


async def before_request(
    app: str,
    resource: str,
    operation: str,
    req: RenderedRequest,
    fields: dict[str, Any],
) -> None:
    if resource == "messages" and operation == "send":
        raw = _build_raw_mime(
            to=str(fields.get("to", "")),
            subject=str(fields.get("subject", "")),
            body=str(fields.get("body", "")),
        )
        req.body = {"raw": raw}
    elif resource == "drafts" and operation == "create":
        raw = _build_raw_mime(
            to=str(fields.get("to", "")),
            subject=str(fields.get("subject", "")),
            body=str(fields.get("body", "")),
        )
        req.body = {"message": {"raw": raw}}


__all__ = ["before_request"]
