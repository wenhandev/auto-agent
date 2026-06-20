from __future__ import annotations

from typing import Any

from app.nodes.integration import IntegrationError


def check_response(
    app: str,
    resource: str,
    operation: str,
    http_out: dict[str, Any],
) -> None:
    payload = http_out.get("json")
    if not isinstance(payload, dict):
        return
    if payload.get("ok") is False:
        error = payload.get("error", "unknown_error")
        raise IntegrationError(f"Slack API error: {error}")


__all__ = ["check_response"]
