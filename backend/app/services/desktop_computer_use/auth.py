"""Local Always-allow / session Allow-once store for desktop apps."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from app.services.desktop_computer_use.forbidden import (
    is_forbidden_app,
    normalize_app_key,
)
from app.services.desktop_computer_use.protocol import DesktopAppAuthorizationError


class DesktopAppAuthStore:
    """Persists Always-allow bundle ids; tracks Allow-once for the process session."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or default_auth_path()
        self._lock = threading.Lock()
        self._always: set[str] = set()
        self._once: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        apps = raw.get("always_allowed") if isinstance(raw, dict) else None
        if isinstance(apps, list):
            self._always = {normalize_app_key(str(a)) for a in apps if str(a).strip()}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"always_allowed": sorted(self._always)}
        self._path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def list_always_allowed(self) -> list[str]:
        with self._lock:
            return sorted(self._always)

    def allow_always(self, app: str) -> None:
        key = normalize_app_key(app)
        if not key:
            return
        if is_forbidden_app(key):
            raise DesktopAppAuthorizationError(f"app is hard-denied: {app}")
        with self._lock:
            self._always.add(key)
            self._save()

    def allow_once(self, app: str) -> None:
        key = normalize_app_key(app)
        if not key:
            return
        if is_forbidden_app(key):
            raise DesktopAppAuthorizationError(f"app is hard-denied: {app}")
        with self._lock:
            self._once.add(key)

    def revoke(self, app: str) -> None:
        key = normalize_app_key(app)
        with self._lock:
            self._always.discard(key)
            self._once.discard(key)
            self._save()

    def clear_once(self) -> None:
        with self._lock:
            self._once.clear()

    def is_authorized(self, app: str, *, bundle_id: str = "", name: str = "") -> bool:
        if is_forbidden_app(app, bundle_id=bundle_id, name=name):
            return False
        keys = {
            normalize_app_key(app),
            normalize_app_key(bundle_id),
            normalize_app_key(name),
        }
        keys.discard("")
        with self._lock:
            return bool(keys & self._always) or bool(keys & self._once)

    def require_authorized(self, app: str, *, bundle_id: str = "", name: str = "") -> None:
        if is_forbidden_app(app, bundle_id=bundle_id, name=name):
            from app.services.desktop_computer_use.protocol import DesktopAppForbiddenError

            raise DesktopAppForbiddenError(f"app is hard-denied: {app}")
        if not self.is_authorized(app, bundle_id=bundle_id, name=name):
            raise DesktopAppAuthorizationError(
                f"app not authorized for Computer Use: {app}"
            )


_DEFAULT_STORE: Optional[DesktopAppAuthStore] = None
_STORE_LOCK = threading.Lock()


def default_auth_path() -> Path:
    return Path.home() / ".auto-agent" / "desktop_computer_use_auth.json"


def get_auth_store() -> DesktopAppAuthStore:
    global _DEFAULT_STORE
    with _STORE_LOCK:
        if _DEFAULT_STORE is None:
            _DEFAULT_STORE = DesktopAppAuthStore()
        return _DEFAULT_STORE


def reset_auth_store_for_tests(path: Optional[Path] = None) -> DesktopAppAuthStore:
    """Replace the process-global store (tests only)."""
    global _DEFAULT_STORE
    with _STORE_LOCK:
        _DEFAULT_STORE = DesktopAppAuthStore(path=path)
        return _DEFAULT_STORE
