"""Same-app concurrency lock for Desktop Computer Use."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Optional

from app.services.desktop_computer_use.forbidden import normalize_app_key


class DesktopAppBusyError(Exception):
    """Raised when another Computer Use holder already owns the app."""


# app_key -> (holder_id, depth)
_REGISTRY: dict[str, tuple[str, int]] = {}
_LOCK = threading.Lock()


def reset_app_locks_for_tests() -> None:
    with _LOCK:
        _REGISTRY.clear()


def current_holder(app: str) -> Optional[str]:
    key = normalize_app_key(app)
    with _LOCK:
        entry = _REGISTRY.get(key)
        return entry[0] if entry else None


@contextmanager
def hold_desktop_app(app: str, holder_id: Optional[str] = None) -> Iterator[str]:
    """Exclusive hold for one app. Raises DesktopAppBusyError if contested.

    Re-entrant for the same holder_id (nested depth counted).
    """
    key = normalize_app_key(app)
    if not key:
        raise ValueError("app is required for desktop lock")
    holder = (holder_id or "").strip() or uuid.uuid4().hex
    with _LOCK:
        existing = _REGISTRY.get(key)
        if existing is not None and existing[0] != holder:
            raise DesktopAppBusyError(
                f"Computer Use already active for app {app!r} "
                f"(holder={existing[0]})"
            )
        depth = existing[1] + 1 if existing else 1
        _REGISTRY[key] = (holder, depth)
    try:
        yield holder
    finally:
        with _LOCK:
            cur = _REGISTRY.get(key)
            if cur is None or cur[0] != holder:
                return
            if cur[1] <= 1:
                del _REGISTRY[key]
            else:
                _REGISTRY[key] = (holder, cur[1] - 1)
