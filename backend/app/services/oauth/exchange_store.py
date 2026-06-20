from __future__ import annotations

import secrets
import time
from typing import Any

EXCHANGE_CODE_TTL_SECONDS = 60

_store: dict[str, dict[str, Any]] = {}


def reset_exchange_store_for_tests() -> None:
    _store.clear()


def issue_exchange_code(*, user_id: str) -> str:
    _purge_expired(_store)
    code = secrets.token_urlsafe(32)
    _store[code] = {
        "user_id": user_id,
        "exp": int(time.time()) + EXCHANGE_CODE_TTL_SECONDS,
    }
    return code


def consume_exchange_code(code: str) -> str | None:
    _purge_expired(_store)
    entry = _store.pop(code, None)
    if entry is None:
        return None
    if int(entry.get("exp", 0)) < int(time.time()):
        return None
    user_id = entry.get("user_id")
    return user_id if isinstance(user_id, str) else None


def _purge_expired(store: dict[str, dict[str, Any]]) -> None:
    now = int(time.time())
    expired = [key for key, entry in store.items() if int(entry.get("exp", 0)) < now]
    for key in expired:
        store.pop(key, None)
