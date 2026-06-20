"""Signature verification for app webhook triggers."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any, Optional

from app.integrations.json_path import resolve_path
from app.integrations.schema import VerificationSpec


class WebhookVerificationError(ValueError):
    pass


def _extract_event_id(payload: dict[str, Any], spec: VerificationSpec) -> str:
    if spec.event_id_path:
        try:
            val = resolve_path(payload, spec.event_id_path)
            return str(val)
        except ValueError:
            pass
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def extract_event_id(payload: dict[str, Any], spec: Optional[VerificationSpec]) -> str:
    if spec is None:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
        ).hexdigest()
    return _extract_event_id(payload, spec)


def verify_hmac(
    raw_body: bytes,
    headers: dict[str, str],
    secret: str,
    spec: VerificationSpec,
) -> None:
    header_name = spec.header or "X-Signature"
    received = headers.get(header_name) or headers.get(header_name.lower())
    if not received:
        raise WebhookVerificationError(f"missing signature header {header_name!r}")

    algo = spec.algorithm or "sha256"
    if algo != "sha256":
        raise WebhookVerificationError(f"unsupported HMAC algorithm {algo!r}")

    if received.startswith("v0="):
        expected = "v0=" + hmac.new(
            secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
    elif received.startswith("sha256="):
        expected = "sha256=" + hmac.new(
            secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
    else:
        expected = hmac.new(
            secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
        if received != expected and received != f"sha256={expected}":
            raise WebhookVerificationError("invalid HMAC signature")
        return

    if not secrets.compare_digest(received, expected):
        raise WebhookVerificationError("invalid HMAC signature")


def verify_shared_secret(
    headers: dict[str, str],
    secret: str,
    spec: VerificationSpec,
) -> None:
    header_name = spec.secret_header or spec.header or "X-Webhook-Secret"
    received = headers.get(header_name) or headers.get(header_name.lower())
    if not received or not secrets.compare_digest(received, secret):
        raise WebhookVerificationError("invalid shared secret")


def verify_event(
    *,
    raw_body: bytes,
    headers: dict[str, str],
    payload: dict[str, Any],
    secret: str,
    spec: VerificationSpec,
) -> str:
    if spec.type == "hmac":
        verify_hmac(raw_body, headers, secret, spec)
    elif spec.type == "shared_secret":
        verify_shared_secret(headers, secret, spec)
    elif spec.type == "challenge":
        pass
    else:
        raise WebhookVerificationError(f"unsupported verification type {spec.type!r}")
    return _extract_event_id(payload, spec)


def challenge_response(
    payload: dict[str, Any],
    spec: VerificationSpec,
) -> Optional[dict[str, Any]]:
    if spec.type != "challenge" and not spec.challenge_field:
        return None
    field = spec.challenge_field or "challenge"
    if field not in payload:
        return None
    response_field = spec.challenge_response_field or field
    return {response_field: payload[field]}


__all__ = [
    "WebhookVerificationError",
    "challenge_response",
    "extract_event_id",
    "verify_event",
]
