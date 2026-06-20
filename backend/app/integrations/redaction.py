from __future__ import annotations

from typing import Any

REDACTED = "***"


def redact_request_summary(summary: dict[str, Any], secret_keys: set[str]) -> dict[str, Any]:
    """Return a copy of *summary* with secret-bearing values replaced."""
    out = dict(summary)
    headers = dict(out.get("headers") or {})
    for key in list(headers.keys()):
        sk = f"header.{key}"
        if sk in secret_keys or key.lower() == "authorization":
            headers[key] = REDACTED
    out["headers"] = headers

    query = dict(out.get("query") or {})
    for key in list(query.keys()):
        if f"query.{key}" in secret_keys:
            query[key] = REDACTED
    out["query"] = query

    return out


__all__ = ["REDACTED", "redact_request_summary"]
