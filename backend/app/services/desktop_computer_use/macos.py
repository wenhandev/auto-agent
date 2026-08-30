"""macOS Foreground DesktopComputerUseBackend (AX + screenshot + CGEvent).

Requires optional extras: `pip install -e '.[desktop-macos]'` (pyobjc).
Without pyobjc, constructing this class raises DesktopComputerUseUnavailableError.
"""

from __future__ import annotations

import asyncio
import subprocess
import uuid
from typing import Any, Optional

from app.services.desktop_computer_use.auth import DesktopAppAuthStore, get_auth_store
from app.services.desktop_computer_use.forbidden import is_forbidden_app
from app.services.desktop_computer_use.protocol import (
    DesktopAppForbiddenError,
    DesktopAppInfo,
    DesktopAppState,
    DesktopComputerUseUnavailableError,
    DesktopElement,
)


def _require_pyobjc() -> None:
    try:
        import AppKit  # noqa: F401
        import ApplicationServices  # noqa: F401
        import Quartz  # noqa: F401
    except ImportError as exc:
        raise DesktopComputerUseUnavailableError(
            "macOS Computer Use requires pyobjc "
            "(pip install -e '.[desktop-macos]')"
        ) from exc


class MacOSDesktopComputerUseBackend:
    """Foreground driver: activates the target app and synthesizes input."""

    provider_id = "macos_foreground"

    def __init__(self, *, auth: Optional[DesktopAppAuthStore] = None) -> None:
        _require_pyobjc()
        self.auth = auth if auth is not None else get_auth_store()
        self._last_elements: dict[str, list[DesktopElement]] = {}
        self._resolved_cache: dict[str, DesktopAppInfo] = {}
        self._last_activated_key: Optional[str] = None

    def _guard(self, app: str, *, bundle_id: str = "", name: str = "") -> None:
        if is_forbidden_app(app, bundle_id=bundle_id, name=name):
            raise DesktopAppForbiddenError(f"app is hard-denied: {app}")
        self.auth.require_authorized(app, bundle_id=bundle_id, name=name)

    async def list_apps(self) -> list[DesktopAppInfo]:
        return await asyncio.to_thread(self._list_apps_sync)

    def _list_apps_sync(self) -> list[DesktopAppInfo]:
        from AppKit import NSWorkspace

        apps: list[DesktopAppInfo] = []
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        front_bid = str(front.bundleIdentifier() or "") if front else ""
        for running in NSWorkspace.sharedWorkspace().runningApplications():
            bid = str(running.bundleIdentifier() or "")
            if not bid or running.isHidden():
                continue
            name = str(running.localizedName() or bid)
            apps.append(
                DesktopAppInfo(
                    app_id=bid,
                    name=name,
                    bundle_id=bid,
                    pid=int(running.processIdentifier()),
                    frontmost=bid == front_bid,
                )
            )
        return apps

    async def open_app(self, app: str) -> DesktopAppInfo:
        info = await self._resolve_app(app)
        self._guard(app, bundle_id=info.bundle_id, name=info.name)
        await asyncio.to_thread(self._activate_sync, info)
        return info

    def _activate_sync(self, info: DesktopAppInfo) -> None:
        from AppKit import NSRunningApplication, NSWorkspace
        from AppKit import NSApplicationActivateIgnoringOtherApps

        key = (info.bundle_id or info.app_id or info.name).lower()
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        front_bid = str(front.bundleIdentifier() or "").lower() if front else ""
        if (
            key
            and key == self._last_activated_key
            and front_bid
            and front_bid == (info.bundle_id or info.app_id).lower()
        ):
            return

        if info.pid:
            running = NSRunningApplication.runningApplicationWithProcessIdentifier_(
                info.pid
            )
            if running is not None:
                running.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
                self._last_activated_key = key
                return
        # Launch by bundle id / name via open.
        target = info.bundle_id or info.name
        subprocess.run(
            ["open", "-b", target] if "." in target else ["open", "-a", target],
            check=False,
            capture_output=True,
        )
        # Best-effort frontmost refresh
        _ = NSWorkspace.sharedWorkspace().frontmostApplication()
        self._last_activated_key = key

    def _pid_still_running(self, pid: int) -> bool:
        try:
            from AppKit import NSRunningApplication

            running = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
            return running is not None and not running.isTerminated()
        except Exception:
            return False

    async def _resolve_app(self, app: str) -> DesktopAppInfo:
        needle = (app or "").strip().lower()
        cached = self._resolved_cache.get(needle)
        if (
            cached is not None
            and cached.pid
            and self._pid_still_running(int(cached.pid))
        ):
            return cached
        if cached is not None:
            self._resolved_cache.pop(needle, None)
        apps = await self.list_apps()
        for info in apps:
            if needle in {
                info.app_id.lower(),
                info.bundle_id.lower(),
                info.name.lower(),
            }:
                self._resolved_cache[needle] = info
                self._resolved_cache[info.app_id.lower()] = info
                if info.bundle_id:
                    self._resolved_cache[info.bundle_id.lower()] = info
                return info
        # Not running — treat argument as bundle id or display name.
        return DesktopAppInfo(app_id=app, name=app, bundle_id=app if "." in app else "")

    async def get_app_state(self, app: str) -> DesktopAppState:
        info = await self._resolve_app(app)
        self._guard(app, bundle_id=info.bundle_id, name=info.name)
        await asyncio.to_thread(self._activate_sync, info)
        return await asyncio.to_thread(self._capture_state_sync, info)

    def _capture_state_sync(self, info: DesktopAppInfo) -> DesktopAppState:
        from AppKit import NSWorkspace
        import ApplicationServices as AS
        import Quartz

        # Resolve pid again after activate.
        pid = info.pid
        if not pid:
            for running in NSWorkspace.sharedWorkspace().runningApplications():
                bid = str(running.bundleIdentifier() or "")
                if bid and bid.lower() in {
                    info.bundle_id.lower(),
                    info.app_id.lower(),
                }:
                    pid = int(running.processIdentifier())
                    info.pid = pid
                    break
        if not pid:
            raise DesktopComputerUseUnavailableError(f"app not running: {info.app_id}")

        ax_app = AS.AXUIElementCreateApplication(pid)
        title = info.name
        err, windows = AS.AXUIElementCopyAttributeValue(
            ax_app, AS.kAXWindowsAttribute, None
        )
        elements: list[DesktopElement] = []
        ax_root: dict[str, Any] = {"role": "application", "name": info.name, "children": []}
        if err == 0 and windows:
            win = windows[0]
            _err_t, title_val = AS.AXUIElementCopyAttributeValue(
                win, AS.kAXTitleAttribute, None
            )
            if title_val:
                title = str(title_val)
            self._walk_ax(win, elements, ax_root)

        screenshot = self._screenshot_front_window(pid)
        ref = f"desktop-{uuid.uuid4().hex[:12]}"
        self._last_elements[info.bundle_id.lower() or info.app_id.lower()] = elements
        # Store artifact when possible.
        try:
            from app.services import artifact_context
            from pathlib import Path

            run_id = artifact_context.get_run_id()
            root = Path(__file__).resolve().parents[3] / ".vision_artifacts"
            if run_id:
                from app.services import artifacts as artifact_svc

                stored = artifact_svc.store_bytes(
                    run_id, f"desktop/{ref}.png", screenshot, content_type="image/png"
                )
                ref = stored or ref
            else:
                root.mkdir(parents=True, exist_ok=True)
                path = root / f"{ref}.png"
                path.write_bytes(screenshot)
        except Exception:
            pass

        return DesktopAppState(
            app=info,
            title=title,
            screenshot_bytes=screenshot,
            screenshot_ref=ref,
            elements=elements,
            ax_snapshot=ax_root,
        )

    def _walk_ax(
        self,
        element: Any,
        out: list[DesktopElement],
        tree_node: dict[str, Any],
        depth: int = 0,
    ) -> None:
        if depth > 25 or len(out) >= 80:
            return
        import ApplicationServices as AS

        role = ""
        name = ""
        value = ""
        _e, role_v = AS.AXUIElementCopyAttributeValue(element, AS.kAXRoleAttribute, None)
        if role_v:
            role = str(role_v).replace("AX", "").lower()
        _e, name_v = AS.AXUIElementCopyAttributeValue(
            element, AS.kAXTitleAttribute, None
        )
        if not name_v:
            _e, name_v = AS.AXUIElementCopyAttributeValue(
                element, AS.kAXDescriptionAttribute, None
            )
        if name_v:
            name = str(name_v)
        _e, val_v = AS.AXUIElementCopyAttributeValue(element, AS.kAXValueAttribute, None)
        if val_v is not None:
            value = str(val_v)

        interactive = role in {
            "button",
            "textfield",
            "textarea",
            "checkbox",
            "radiobutton",
            "popupbutton",
            "menuitem",
            "link",
            "tab",
            "slider",
            "combobox",
            "incrementor",
            "disclosuretriangle",
        } or role in {"statictext"} and bool(name)

        child_node: dict[str, Any] = {
            "role": role or "generic",
            "name": name,
            "value": value,
            "children": [],
        }
        tree_node.setdefault("children", []).append(child_node)

        if interactive and (name or value or role in {"textfield", "textarea", "button"}):
            x = y = w = h = 0.0
            _e, pos = AS.AXUIElementCopyAttributeValue(
                element, AS.kAXPositionAttribute, None
            )
            _e, size = AS.AXUIElementCopyAttributeValue(
                element, AS.kAXSizeAttribute, None
            )
            if pos is not None:
                try:
                    x = float(pos.x)
                    y = float(pos.y)
                except Exception:
                    pass
            if size is not None:
                try:
                    w = float(size.width)
                    h = float(size.height)
                except Exception:
                    pass
            out.append(
                DesktopElement(
                    index=len(out),
                    role=role or "generic",
                    name=name,
                    value=value,
                    x=x,
                    y=y,
                    width=w,
                    height=h,
                    ax_ref=f"ax-{len(out)}",
                )
            )

        _e, children = AS.AXUIElementCopyAttributeValue(
            element, AS.kAXChildrenAttribute, None
        )
        if _e == 0 and children:
            for child in children:
                self._walk_ax(child, out, child_node, depth + 1)

    def _screenshot_front_window(self, pid: int) -> bytes:
        import Quartz
        from Quartz import (
            CGWindowListCopyWindowInfo,
            CGWindowListCreateImage,
            kCGWindowListOptionOnScreenOnly,
            kCGWindowImageDefault,
            kCGNullWindowID,
            CGRectNull,
        )
        import Cocoa

        window_id = None
        infos = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
        for info in infos or []:
            if int(info.get("kCGWindowOwnerPID", -1)) == pid:
                window_id = int(info.get("kCGWindowNumber", 0))
                if window_id:
                    break
        if not window_id:
            # Full display fallback
            image = CGWindowListCreateImage(
                CGRectNull,
                kCGWindowListOptionOnScreenOnly,
                kCGNullWindowID,
                kCGWindowImageDefault,
            )
        else:
            image = CGWindowListCreateImage(
                CGRectNull,
                Quartz.kCGWindowListOptionIncludingWindow,
                window_id,
                kCGWindowImageDefault,
            )
        if image is None:
            return b""
        rep = Cocoa.NSBitmapImageRep.alloc().initWithCGImage_(image)
        data = rep.representationUsingType_properties_(Cocoa.NSPNGFileType, None)
        return bytes(data) if data is not None else b""

    def _elements_for(self, app: str) -> list[DesktopElement]:
        key = (app or "").strip().lower()
        if key in self._last_elements:
            return self._last_elements[key]
        for k, els in self._last_elements.items():
            if key in k or k in key:
                return els
        return []

    async def click(
        self,
        app: str,
        *,
        index: Optional[int] = None,
        x: Optional[float] = None,
        y: Optional[float] = None,
    ) -> dict[str, Any]:
        info = await self._resolve_app(app)
        self._guard(app, bundle_id=info.bundle_id, name=info.name)
        await asyncio.to_thread(self._activate_sync, info)
        if index is not None:
            els = self._elements_for(info.bundle_id or info.app_id)
            if index < 0 or index >= len(els):
                raise IndexError(f"element index out of range: {index}")
            cx, cy = els[index].center
            x, y = cx, cy
        if x is None or y is None:
            raise ValueError("click requires index or x/y")
        await asyncio.to_thread(self._click_sync, float(x), float(y))
        return {
            "ok": True,
            "action": "click",
            "app": info.app_id,
            "index": index,
            "coordinates": {"x": x, "y": y},
        }

    def _click_sync(self, x: float, y: float) -> None:
        import Quartz

        Quartz.CGWarpMouseCursorPosition((x, y))
        for down in (True, False):
            ev = Quartz.CGEventCreateMouseEvent(
                None,
                Quartz.kCGEventLeftMouseDown if down else Quartz.kCGEventLeftMouseUp,
                (x, y),
                Quartz.kCGMouseButtonLeft,
            )
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)

    async def type_text(
        self,
        app: str,
        text: str,
        *,
        index: Optional[int] = None,
    ) -> dict[str, Any]:
        info = await self._resolve_app(app)
        self._guard(app, bundle_id=info.bundle_id, name=info.name)
        await asyncio.to_thread(self._activate_sync, info)
        if index is not None:
            await self.click(app, index=index)
        await asyncio.to_thread(self._type_sync, text)
        return {"ok": True, "action": "type_text", "app": info.app_id, "index": index}

    def _type_sync(self, text: str) -> None:
        import Quartz

        # CGEventKeyboardSetUnicodeString is limited (~20 UniChars). Chunk.
        chunk_size = 20
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            if not chunk:
                continue
            try:
                ev_down = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
                Quartz.CGEventKeyboardSetUnicodeString(ev_down, len(chunk), chunk)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev_down)
                ev_up = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
                Quartz.CGEventKeyboardSetUnicodeString(ev_up, len(chunk), chunk)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev_up)
            except Exception:
                for ch in chunk:
                    ev_down = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
                    Quartz.CGEventKeyboardSetUnicodeString(ev_down, len(ch), ch)
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev_down)
                    ev_up = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
                    Quartz.CGEventKeyboardSetUnicodeString(ev_up, len(ch), ch)
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev_up)

    async def key(self, app: str, key: str) -> dict[str, Any]:
        info = await self._resolve_app(app)
        self._guard(app, bundle_id=info.bundle_id, name=info.name)
        await asyncio.to_thread(self._activate_sync, info)
        await asyncio.to_thread(self._key_sync, key)
        return {"ok": True, "action": "key", "app": info.app_id, "key": key}

    def _key_sync(self, key: str) -> None:
        import Quartz

        mapping = {
            "return": 36,
            "enter": 36,
            "tab": 48,
            "escape": 53,
            "delete": 51,
            "backspace": 51,
            "space": 49,
            "up": 126,
            "down": 125,
            "left": 123,
            "right": 124,
        }
        code = mapping.get(key.lower())
        if code is None:
            self._type_sync(key)
            return
        for down in (True, False):
            ev = Quartz.CGEventCreateKeyboardEvent(None, code, down)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)

    async def scroll(
        self,
        app: str,
        direction: str,
        amount: int = 3,
    ) -> dict[str, Any]:
        info = await self._resolve_app(app)
        self._guard(app, bundle_id=info.bundle_id, name=info.name)
        await asyncio.to_thread(self._activate_sync, info)
        await asyncio.to_thread(self._scroll_sync, direction, amount)
        return {
            "ok": True,
            "action": "scroll",
            "app": info.app_id,
            "direction": direction,
            "amount": amount,
        }

    def _scroll_sync(self, direction: str, amount: int) -> None:
        import Quartz

        dy = amount if direction in ("up", "top") else -amount if direction in ("down", "bottom") else 0
        dx = amount if direction == "left" else -amount if direction == "right" else 0
        ev = Quartz.CGEventCreateScrollWheelEvent(
            None, Quartz.kCGScrollEventUnitLine, 2, dy, dx
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)
