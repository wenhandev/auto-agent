from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from app.auth.session import _b64url_decode, _b64url_encode

OAUTH_STATE_COOKIE = "auto_agent_oauth_state"
OAUTH_STATE_TTL_SECONDS = 600


def _sign(payload_b64: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return _b64url_encode(digest)


def pack_oauth_state_cookie(
    *,
    secret: str,
    provider: str,
    state: str,
    code_verifier: str,
) -> str:
    payload: dict[str, Any] = {
        "p": provider,
        "s": state,
        "v": code_verifier,
        "exp": int(time.time()) + OAUTH_STATE_TTL_SECONDS,
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    return f"{payload_b64}.{_sign(payload_b64, secret)}"


def unpack_oauth_state_cookie(value: str, *, secret: str) -> dict[str, str] | None:
    try:
        payload_b64, signature = value.split(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(signature, _sign(payload_b64, secret)):
        return None
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at < int(time.time()):
        return None
    provider = payload.get("p")
    state = payload.get("s")
    verifier = payload.get("v")
    if not all(isinstance(x, str) and x for x in (provider, state, verifier)):
        return None
    return {"provider": provider, "state": state, "code_verifier": verifier}
