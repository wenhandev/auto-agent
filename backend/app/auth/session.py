"""Session JWT creation, verification, and login rate limiting."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.settings import settings

SESSION_COOKIE = "session_token"
SESSION_TTL_SECONDS = 7 * 24 * 3600
LOGIN_RATE_LIMIT = 10
LOGIN_RATE_WINDOW_SECONDS = 60


@dataclass
class _LoginBucket:
    count: int = 0
    window_start: float = field(default_factory=time.monotonic)


_login_buckets: dict[str, _LoginBucket] = {}


def reset_login_rate_limiter_for_tests() -> None:
    _login_buckets.clear()


def _secret() -> bytes:
    return (settings.session_secret or "change-me-in-production").encode("utf-8")


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def create_session_token(user_id: str, *, ttl_seconds: int = SESSION_TTL_SECONDS) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": user_id, "iat": now, "exp": now + ttl_seconds}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = hmac.new(_secret(), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(sig)}"


def verify_session_token(token: str) -> Optional[str]:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".", 2)
    except ValueError:
        return None
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(_secret(), signing_input, hashlib.sha256).digest()
    try:
        actual = _b64url_decode(sig_b64)
    except Exception:
        return None
    if not hmac.compare_digest(expected, actual):
        return None
    try:
        payload: dict[str, Any] = json.loads(_b64url_decode(payload_b64))
    except Exception:
        return None
    exp = payload.get("exp")
    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        return None
    if isinstance(exp, (int, float)) and int(exp) < int(time.time()):
        return None
    return sub


def extract_bearer_session(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def check_login_rate_limit(bucket_key: str) -> None:
    from fastapi import HTTPException

    now = time.monotonic()
    bucket = _login_buckets.get(bucket_key)
    if bucket is None or now - bucket.window_start >= LOGIN_RATE_WINDOW_SECONDS:
        bucket = _LoginBucket(count=0, window_start=now)
        _login_buckets[bucket_key] = bucket
    bucket.count += 1
    if bucket.count > LOGIN_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="too many login attempts")


__all__ = [
    "SESSION_COOKIE",
    "SESSION_TTL_SECONDS",
    "check_login_rate_limit",
    "create_session_token",
    "extract_bearer_session",
    "reset_login_rate_limiter_for_tests",
    "verify_session_token",
]
