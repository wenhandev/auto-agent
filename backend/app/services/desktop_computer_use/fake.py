"""In-memory DesktopComputerUseBackend for unit tests."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from app.services.desktop_computer_use.auth import DesktopAppAuthStore
from app.services.desktop_computer_use.forbidden import is_forbidden_app
from app.services.desktop_computer_use.protocol import (
    DesktopAppAuthorizationError,
    DesktopAppForbiddenError,
    DesktopAppInfo,
    DesktopAppState,
    DesktopElement,
)


_MIN_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeDesktopComputerUseBackend:
    provider_id = "fake"

    def __init__(
        self,
        *,
        auth: Optional[DesktopAppAuthStore] = None,
        apps: Optional[dict[str, dict[str, Any]]] = None,
    ) -> None:
        self.auth = auth
        self._apps: dict[str, dict[str, Any]] = {}
        self._states: dict[str, DesktopAppState] = {}
        self.actions: list[dict[str, Any]] = []
        if apps:
            for key, spec in apps.items():
                self.seed_app(key, **spec)
        else:
            self.seed_app(
                "com.apple.TextEdit",
                name="TextEdit",
                title="Untitled",
                elements=[
                    {"role": "textfield", "name": "text area", "value": ""},
                    {"role": "button", "name": "Save"},
                ],
            )

    def seed_app(
        self,
        app_id: str,
        *,
        name: str = "",
        title: str = "",
        elements: Optional[list[dict[str, Any]]] = None,
        frontmost: bool = False,
    ) -> None:
        key = app_id.strip()
        info = DesktopAppInfo(
            app_id=key,
            name=name or key.split(".")[-1],
            bundle_id=key,
            frontmost=frontmost,
        )
        els = [
            DesktopElement(
                index=i,
                role=str(e.get("role") or "generic"),
                name=str(e.get("name") or ""),
                value=str(e.get("value") or ""),
                x=float(e.get("x") or 10 + i * 20),
                y=float(e.get("y") or 40),
                width=float(e.get("width") or 80),
                height=float(e.get("height") or 24),
                ax_ref=f"fake-{i}",
            )
            for i, e in enumerate(elements or [])
        ]
        self._apps[key.lower()] = {"info": info}
        self._states[key.lower()] = DesktopAppState(
            app=info,
            title=title or info.name,
            screenshot_bytes=_MIN_PNG,
            screenshot_ref=f"fake-{uuid.uuid4().hex[:8]}",
            elements=els,
            ax_snapshot={
                "role": "window",
                "name": title or info.name,
                "children": [
                    {"role": el.role, "name": el.name, "value": el.value}
                    for el in els
                ],
            },
        )

    def _resolve_key(self, app: str) -> str:
        needle = (app or "").strip().lower()
        if needle in self._apps:
            return needle
        for key, meta in self._apps.items():
            info: DesktopAppInfo = meta["info"]
            if needle in {
                info.app_id.lower(),
                info.bundle_id.lower(),
                info.name.lower(),
            }:
                return key
        raise KeyError(f"unknown app: {app}")

    def _guard(self, app: str) -> DesktopAppInfo:
        if is_forbidden_app(app):
            raise DesktopAppForbiddenError(f"app is hard-denied: {app}")
        key = self._resolve_key(app)
        info: DesktopAppInfo = self._apps[key]["info"]
        if is_forbidden_app(info.app_id, bundle_id=info.bundle_id, name=info.name):
            raise DesktopAppForbiddenError(f"app is hard-denied: {app}")
        if self.auth is not None:
            self.auth.require_authorized(
                app, bundle_id=info.bundle_id, name=info.name
            )
        return info

    async def list_apps(self) -> list[DesktopAppInfo]:
        return [meta["info"] for meta in self._apps.values()]

    async def open_app(self, app: str) -> DesktopAppInfo:
        info = self._guard(app)
        info.frontmost = True
        self.actions.append({"action": "open_app", "app": info.app_id})
        return info

    async def get_app_state(self, app: str) -> DesktopAppState:
        info = self._guard(app)
        key = self._resolve_key(info.app_id)
        state = self._states[key]
        # Refresh screenshot_ref each capture (indices stay until next mutate).
        state.screenshot_ref = f"fake-{uuid.uuid4().hex[:8]}"
        state.screenshot_bytes = _MIN_PNG
        self.actions.append({"action": "get_app_state", "app": info.app_id})
        return state

    def _element(self, app: str, index: int) -> DesktopElement:
        key = self._resolve_key(app)
        state = self._states[key]
        for el in state.elements:
            if el.index == index:
                return el
        raise IndexError(f"element index out of range: {index}")

    async def click(
        self,
        app: str,
        *,
        index: Optional[int] = None,
        x: Optional[float] = None,
        y: Optional[float] = None,
    ) -> dict[str, Any]:
        info = self._guard(app)
        payload: dict[str, Any] = {"action": "click", "app": info.app_id}
        if index is not None:
            el = self._element(info.app_id, index)
            payload["index"] = index
            payload["target"] = {"role": el.role, "name": el.name}
        else:
            payload["coordinates"] = {"x": x, "y": y}
        self.actions.append(payload)
        return {"ok": True, **payload}

    async def type_text(
        self,
        app: str,
        text: str,
        *,
        index: Optional[int] = None,
    ) -> dict[str, Any]:
        info = self._guard(app)
        if index is not None:
            el = self._element(info.app_id, index)
            el.value = (el.value or "") + text
            # Keep ax snapshot in sync for perception.
            key = self._resolve_key(info.app_id)
            children = self._states[key].ax_snapshot.get("children") or []
            if 0 <= index < len(children) and isinstance(children[index], dict):
                children[index]["value"] = el.value
        payload = {
            "action": "type_text",
            "app": info.app_id,
            "text": text,
            "index": index,
        }
        self.actions.append(payload)
        return {"ok": True, **payload}

    async def key(self, app: str, key: str) -> dict[str, Any]:
        info = self._guard(app)
        payload = {"action": "key", "app": info.app_id, "key": key}
        self.actions.append(payload)
        return {"ok": True, **payload}

    async def scroll(
        self,
        app: str,
        direction: str,
        amount: int = 3,
    ) -> dict[str, Any]:
        info = self._guard(app)
        payload = {
            "action": "scroll",
            "app": info.app_id,
            "direction": direction,
            "amount": amount,
        }
        self.actions.append(payload)
        return {"ok": True, **payload}
