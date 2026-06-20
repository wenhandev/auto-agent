"""HMAC signing helpers for outbound and inbound webhooks."""
from __future__ import annotations

import hashlib
import hmac
import secrets

SIGNATURE_HEADER = "X-AutoAgent-Signature"
DELIVERY_ID_HEADER = "X-AutoAgent-Delivery-Id"


def sign_body(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(body: bytes, secret: str, header_value: str) -> bool:
    if not header_value:
        return False
    received = header_value.strip()
    expected = sign_body(body, secret)
    if secrets.compare_digest(received, expected):
        return True
    bare = expected.removeprefix("sha256=")
    if secrets.compare_digest(received, bare):
        return True
    if received.startswith("sha256="):
        return secrets.compare_digest(received, expected)
    return False


__all__ = [
    "DELIVERY_ID_HEADER",
    "SIGNATURE_HEADER",
    "sign_body",
    "verify_signature",
]
