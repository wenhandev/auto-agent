"""Receiver-side webhook signature verification (copy into your integration).

Verification recipe:
1. Read the raw request body bytes (before JSON parsing).
2. Read the ``X-AutoAgent-Signature`` header (format ``sha256=<hex>``).
3. Compute ``HMAC-SHA256(secret, body)`` and prefix with ``sha256=``.
4. Compare with ``secrets.compare_digest`` (constant-time).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

SIGNATURE_HEADER = "X-AutoAgent-Signature"
DELIVERY_ID_HEADER = "X-AutoAgent-Delivery-Id"


def expected_signature(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_webhook(body: bytes, secret: str, signature_header: str) -> bool:
    if not signature_header:
        return False
    received = signature_header.strip()
    expected = expected_signature(body, secret)
    if secrets.compare_digest(received, expected):
        return True
    bare = expected.removeprefix("sha256=")
    return secrets.compare_digest(received, bare)


__all__ = [
    "DELIVERY_ID_HEADER",
    "SIGNATURE_HEADER",
    "expected_signature",
    "verify_webhook",
]
