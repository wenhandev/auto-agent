"""Shared HTTP client helpers for the http_request node."""
from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

TEXT_CAP = 1_048_576  # 1 MB


class SSRFError(ValueError):
    """Raised when a URL targets a blocked host or scheme."""


def _is_blocked_host(host: str) -> bool:
    if not host:
        return True
    lowered = host.lower().strip("[]")
    if lowered in ("localhost", "0.0.0.0"):
        return True
    if lowered.endswith(".localhost") or lowered.endswith(".local"):
        return True
    try:
        addr = ipaddress.ip_address(lowered)
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror:
            return False
        for info in infos:
            ip = info[4][0]
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                return True
        return False
    return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved


def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFError(f"unsupported URL scheme {parsed.scheme!r}; only http/https allowed")
    if not parsed.hostname:
        raise SSRFError("URL must include a hostname")
    if _is_blocked_host(parsed.hostname):
        raise SSRFError(f"URL host {parsed.hostname!r} is blocked by SSRF policy")
    return url


def _prepare_body(
    body: Any,
    body_kind: str,
) -> tuple[Any, dict[str, str] | None]:
    if body_kind == "none" or body is None:
        return None, None
    if body_kind == "text":
        return str(body), None
    if body_kind == "form":
        if not isinstance(body, dict):
            raise ValueError("body_kind=form requires body to be a dict")
        return body, None
    # json (default)
    return body, {"Content-Type": "application/json"}


def _parse_json_response(content_type: str | None, text: str) -> Any | None:
    if not content_type or "application/json" not in content_type.lower():
        return None
    try:
        import json

        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _truncate_text(text: str) -> tuple[str, bool]:
    if len(text) <= TEXT_CAP:
        return text, False
    return text[:TEXT_CAP], True


async def request(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: Any = None,
    body_kind: str = "json",
    timeout_ms: int = 15_000,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """Issue an HTTP request and return the canonical output shape."""
    validate_url(url)
    req_headers = dict(headers or {})
    content, extra_headers = _prepare_body(body, body_kind)
    if extra_headers:
        for k, v in extra_headers.items():
            req_headers.setdefault(k, v)

    timeout = httpx.Timeout(timeout_ms / 1000)
    async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
        kwargs: dict[str, Any] = {"headers": req_headers}
        if content is not None:
            if body_kind == "json" and not isinstance(content, (str, bytes)):
                kwargs["json"] = content
            elif body_kind == "form":
                kwargs["data"] = content
            else:
                kwargs["content"] = content if isinstance(content, bytes) else str(content)

        resp = await client.request(method.upper(), url, **kwargs)

    raw = resp.text
    try:
        elapsed_ms = int(resp.elapsed.total_seconds() * 1000)
    except RuntimeError:
        elapsed_ms = 0
    text, truncated = _truncate_text(raw)
    out: dict[str, Any] = {
        "status": resp.status_code,
        "headers": dict(resp.headers),
        "json": _parse_json_response(resp.headers.get("content-type"), raw),
        "text": text,
        "elapsed_ms": elapsed_ms,
    }
    if truncated:
        out["text_truncated"] = True
    return out


__all__ = ["SSRFError", "request", "validate_url", "TEXT_CAP"]
