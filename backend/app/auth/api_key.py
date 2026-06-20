"""Bearer / x-api-key authentication and per-key rate limiting."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlmodel import Session

from app.auth.context import auth_context_from_api_key
from app.db.models import ApiKey
from app.db.session import get_session
from app.services import api_keys as api_key_svc
from app.settings import settings


@dataclass
class _TokenBucket:
    tokens: float
    last_refill: float = field(default_factory=time.monotonic)


_buckets: dict[str, _TokenBucket] = {}
_rate_limit_per_min: Optional[int] = None


def _limit_per_min() -> int:
    global _rate_limit_per_min
    if _rate_limit_per_min is None:
        _rate_limit_per_min = max(1, settings.rate_limit_per_min)
    return _rate_limit_per_min


def reset_rate_limiter_for_tests() -> None:
    """Clear in-memory buckets (test helper)."""
    _buckets.clear()
    global _rate_limit_per_min
    _rate_limit_per_min = None


def _extract_plaintext(
    authorization: Optional[str],
    x_api_key: Optional[str],
) -> Optional[str]:
    if x_api_key:
        return x_api_key.strip()
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            return token.strip()
    return None


def _check_rate_limit(bucket_key: str) -> None:
    limit = _limit_per_min()
    refill_rate = limit / 60.0
    now = time.monotonic()
    bucket = _buckets.get(bucket_key)
    if bucket is None:
        bucket = _TokenBucket(tokens=float(limit), last_refill=now)
        _buckets[bucket_key] = bucket
    elapsed = now - bucket.last_refill
    bucket.tokens = min(float(limit), bucket.tokens + elapsed * refill_rate)
    bucket.last_refill = now
    if bucket.tokens < 1.0:
        retry_after = max(1, int((1.0 - bucket.tokens) / refill_rate))
        raise HTTPException(
            status_code=429,
            detail="rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
    bucket.tokens -= 1.0


def authenticate_api_key(
    session: Session,
    authorization: Optional[str] = None,
    x_api_key: Optional[str] = None,
    *,
    update_last_used: bool = True,
    check_rate_limit: bool = True,
) -> ApiKey:
    plaintext = _extract_plaintext(authorization, x_api_key)
    if not plaintext:
        raise HTTPException(status_code=401, detail="missing API key")
    row = api_key_svc.lookup_by_plaintext(session, plaintext)
    if row is None:
        raise HTTPException(status_code=401, detail="invalid API key")
    if check_rate_limit:
        from app.services import orgs as org_svc

        org_id = row.org_id or org_svc.get_default_org_id_from_engine()
        _check_rate_limit(f"org:{org_id}")
    if update_last_used:
        api_key_svc.touch_last_used(session, row)
    auth_context_from_api_key(row)
    return row


async def require_api_key(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    session: Session = Depends(get_session),
) -> ApiKey:
    return authenticate_api_key(session, authorization, x_api_key)


async def require_api_key_or_bootstrap(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    session: Session = Depends(get_session),
) -> Optional[ApiKey]:
    """Allow unauthenticated access only when no active keys exist (bootstrap)."""
    if api_key_svc.count_active_keys(session) == 0:
        return None
    return authenticate_api_key(session, authorization, x_api_key)


__all__ = [
    "authenticate_api_key",
    "require_api_key",
    "require_api_key_or_bootstrap",
    "reset_rate_limiter_for_tests",
]
