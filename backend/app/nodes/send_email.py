from __future__ import annotations

from typing import Any

from app.nodes.result import Item


class SendEmailNotConfiguredError(NotImplementedError):
    """SMTP sending is not configured in this build."""


async def run(
    params: dict[str, Any],
    *,
    input_items: list[Item],
    context: dict[str, Any],
    workflow_id: str | None = None,
    session: Any = None,
) -> list[Item]:
    raise SendEmailNotConfiguredError(
        "send_email is not yet configured: install aiosmtplib and configure an "
        "smtp credential (host, port, username, password, use_tls) to enable SMTP"
    )
