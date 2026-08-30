"""Windows Foreground DesktopComputerUseBackend (UIA + screenshot + SendInput).

Requires optional extras: `pip install -e '.[desktop-windows]'` (pywinauto, Pillow).
Without those deps, constructing this class raises DesktopComputerUseUnavailableError.
"""

from __future__ import annotations

import asyncio
import io
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

# UIA control types we treat as interactive (mirrors macOS AX roles).
_INTERACTIVE_TYPES = frozenset({
    "Button",
    "Edit",
    "CheckBox",
    "RadioButton",
    "ComboBox",
    "ListItem",
    "MenuItem",
    "Hyperlink",
    "TabItem",
    "Slider",
    "Spinner",
    "SplitButton",
    "TreeItem",
    "Document",
    "Text",
})


def _require_windows_deps() -> None:
    try:
        import pywinauto  # noqa: F401
        from PIL import ImageGrab  # noqa: F401
    except ImportError as exc:
        raise DesktopComputerUseUnavailableError(
            "Windows Computer Use requires pywinauto and Pillow "
            "(pip install -e '.[desktop-windows]')"
        ) from exc


def _foreground_hwnd() -> Optional[int]:
    try:
        import ctypes

        hwnd = int(ctypes.windll.user32.GetForegroundWindow())  # type: ignore[attr-defined]
        return hwnd or None
    except Exception:
        return None


def launch_windows_app_controlled(target: str) -> None:
    """Launch via `cmd /c start` only — never unrestricted shell=True."""
    target = (target or "").strip()
    if not target:
        raise DesktopComputerUseUnavailableError("empty Windows app launch target")
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", target],
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        raise DesktopComputerUseUnavailableError(
            f"controlled launch failed for Windows app: {target}"
        ) from exc


class WindowsDesktopComputerUseBackend:
    """Foreground driver: focuses the target window and synthesizes input via UIA."""

    provider_id = "windows_foreground"

    def __init__(self, *, auth: Optional[DesktopAppAuthStore] = None) -> None:
        _require_windows_deps()
        self.auth = auth if auth is not None else get_auth_store()
        self._last_elements: dict[str, list[DesktopElement]] = {}
        self._window_cache: dict[str, Any] = {}
        self._resolved_cache: dict[str, DesktopAppInfo] = {}
        self._last_activated_key: Optional[str] = None

    def _guard(self, app: str, *, bundle_id: str = "", name: str = "") -> None:
        if is_forbidden_app(app, bundle_id=bundle_id, name=name):
            raise DesktopAppForbiddenError(f"app is hard-denied: {app}")
        self.auth.require_authorized(app, bundle_id=bundle_id, name=name)

    async def list_apps(self) -> list[DesktopAppInfo]:
        return await asyncio.to_thread(self._list_apps_sync)

    def _list_apps_sync(self) -> list[DesktopAppInfo]:
        from pywinauto import Desktop

        apps: list[DesktopAppInfo] = []
        fg = _foreground_hwnd()
        for win in Desktop(backend="uia").windows():
            try:
                if not win.is_visible():
                    continue
                title = (win.window_text() or "").strip()
                if not title:
                    continue
                handle = int(win.handle)
                pid = int(win.process_id())
                exe = self._exe_for_pid(pid) or title
                app_id = f"{exe}|{handle}"
                is_front = bool(fg and handle == fg)
                apps.append(
                    DesktopAppInfo(
                        app_id=app_id,
                        name=title,
                        bundle_id=exe,
                        pid=pid,
                        frontmost=is_front,
                    )
                )
                self._window_cache[app_id.lower()] = win
                self._window_cache[str(handle)] = win
                # Only bind exe/title to frontmost (or first) window to avoid
                # last-writer-wins stealing focus across multi-instance apps.
                exe_key = exe.lower()
                if is_front or exe_key not in self._window_cache:
                    self._window_cache[exe_key] = win
                title_key = title.lower()
                if is_front or title_key not in self._window_cache:
                    self._window_cache[title_key] = win
            except Exception:
                continue
        return apps

    def _exe_for_pid(self, pid: int) -> str:
        try:
            import win32process  # type: ignore
            import win32api  # type: ignore
            import win32con  # type: ignore

            handle = win32api.OpenProcess(
                win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            try:
                path = win32process.GetModuleFileNameEx(handle, 0)
                return path.rsplit("\\", 1)[-1] if path else ""
            finally:
                win32api.CloseHandle(handle)
        except Exception:
            return ""

    async def open_app(self, app: str) -> DesktopAppInfo:
        info = await self._resolve_app(app)
        self._guard(app, bundle_id=info.bundle_id, name=info.name)
        await asyncio.to_thread(self._activate_sync, info)
        return info

    def _activate_sync(self, info: DesktopAppInfo) -> None:
        key = (info.app_id or info.bundle_id or info.name).lower()
        # Use live foreground HWND — never trust a stale info.frontmost flag.
        fg = _foreground_hwnd()
        handle = None
        if "|" in (info.app_id or ""):
            try:
                handle = int(info.app_id.rsplit("|", 1)[-1])
            except ValueError:
                handle = None
        if (
            key
            and key == self._last_activated_key
            and handle is not None
            and fg is not None
            and handle == fg
        ):
            return
        win = self._find_window(info)
        if win is not None:
            try:
                win.set_focus()
                self._last_activated_key = key
                return
            except Exception:
                pass
        target = info.bundle_id or info.app_id.split("|", 1)[0] or info.name
        launch_windows_app_controlled(target)
        # Re-resolve after controlled launch; fail clearly if still missing.
        self._list_apps_sync()
        win = self._find_window(info)
        if win is None:
            raise DesktopComputerUseUnavailableError(
                f"could not open or focus Windows app: {target}"
            )
        try:
            win.set_focus()
            self._last_activated_key = key
        except Exception as exc:
            raise DesktopComputerUseUnavailableError(
                f"could not focus Windows app: {target}"
            ) from exc

    def _find_window(self, info: DesktopAppInfo) -> Any:
        # Prefer exact app_id (exe|handle) / handle keys before fuzzy exe/title.
        keys = [
            (info.app_id or "").lower(),
        ]
        if "|" in (info.app_id or ""):
            keys.append(info.app_id.rsplit("|", 1)[-1])
        keys.extend(
            [
                (info.name or "").lower(),
                (info.bundle_id or "").lower(),
            ]
        )
        for key in keys:
            if key and key in self._window_cache:
                return self._window_cache[key]
        # Refresh list then retry
        self._list_apps_sync()
        for key in keys:
            if key and key in self._window_cache:
                return self._window_cache[key]
        return None

    async def _resolve_app(self, app: str) -> DesktopAppInfo:
        needle = (app or "").strip().lower()
        apps = await self.list_apps()
        matches: list[DesktopAppInfo] = []
        for info in apps:
            if needle in {
                info.app_id.lower(),
                info.bundle_id.lower(),
                info.name.lower(),
            } or needle in info.name.lower() or needle in info.app_id.lower():
                matches.append(info)
        if matches:
            # Prefer frontmost, then exact app_id / handle matches.
            matches.sort(
                key=lambda i: (
                    0 if i.frontmost else 1,
                    0 if i.app_id.lower() == needle else 1,
                    0 if i.name.lower() == needle else 1,
                )
            )
            info = matches[0]
            self._resolved_cache[needle] = info
            self._resolved_cache[info.app_id.lower()] = info
            if info.bundle_id:
                self._resolved_cache[info.bundle_id.lower()] = info
            return info
        return DesktopAppInfo(app_id=app, name=app, bundle_id=app)

    async def get_app_state(self, app: str) -> DesktopAppState:
        info = await self._resolve_app(app)
        self._guard(app, bundle_id=info.bundle_id, name=info.name)
        await asyncio.to_thread(self._activate_sync, info)
        return await asyncio.to_thread(self._capture_state_sync, info)

    def _capture_state_sync(self, info: DesktopAppInfo) -> DesktopAppState:
        win = self._find_window(info)
        if win is None:
            raise DesktopComputerUseUnavailableError(f"app window not found: {info.app_id}")

        elements: list[DesktopElement] = []
        ax_root: dict[str, Any] = {
            "role": "window",
            "name": info.name,
            "children": [],
        }
        try:
            self._walk_uia(win, elements, ax_root, depth=0)
        except Exception:
            pass

        screenshot = self._screenshot_window(win)
        ref = f"desktop-{uuid.uuid4().hex[:12]}"
        cache_key = (info.bundle_id or info.app_id).lower()
        self._last_elements[cache_key] = elements

        try:
            from pathlib import Path

            from app.services import artifact_context

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
                (root / f"{ref}.png").write_bytes(screenshot)
        except Exception:
            pass

        return DesktopAppState(
            app=info,
            title=info.name,
            screenshot_bytes=screenshot,
            screenshot_ref=ref,
            elements=elements,
            ax_snapshot=ax_root,
        )

    def _walk_uia(
        self,
        element: Any,
        out: list[DesktopElement],
        tree_node: dict[str, Any],
        depth: int,
    ) -> None:
        if depth > 20 or len(out) >= 80:
            return
        try:
            ctrl_type = str(element.element_info.control_type or "Unknown")
            name = str(element.window_text() or element.element_info.name or "")
            value = ""
            try:
                value = str(element.get_value() or "")
            except Exception:
                pass
            rect = element.rectangle()
            x, y = float(rect.left), float(rect.top)
            w, h = float(rect.width()), float(rect.height())
        except Exception:
            return

        child_node: dict[str, Any] = {
            "role": ctrl_type.lower(),
            "name": name,
            "value": value,
            "children": [],
        }
        tree_node.setdefault("children", []).append(child_node)

        role_norm = ctrl_type
        interactive = role_norm in _INTERACTIVE_TYPES and (
            bool(name) or role_norm in {"Edit", "Document", "Button"}
        )
        if interactive:
            mapped = {
                "Button": "button",
                "Edit": "textfield",
                "Document": "textarea",
                "CheckBox": "checkbox",
                "RadioButton": "radio",
                "ComboBox": "combobox",
                "MenuItem": "menuitem",
                "Hyperlink": "link",
                "TabItem": "tab",
                "Slider": "slider",
                "Text": "statictext",
            }.get(role_norm, role_norm.lower())
            out.append(
                DesktopElement(
                    index=len(out),
                    role=mapped,
                    name=name,
                    value=value,
                    x=x,
                    y=y,
                    width=w,
                    height=h,
                    ax_ref=f"uia-{len(out)}",
                )
            )

        try:
            children = element.children()
        except Exception:
            children = []
        for child in children or []:
            self._walk_uia(child, out, child_node, depth + 1)

    def _screenshot_window(self, win: Any) -> bytes:
        from PIL import ImageGrab

        try:
            rect = win.rectangle()
            bbox = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
            img = ImageGrab.grab(bbox=bbox, all_screens=True)
        except Exception:
            img = ImageGrab.grab(all_screens=True)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

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
            x, y = els[index].center
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
        from pywinauto import mouse

        mouse.click(coords=(int(x), int(y)))

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
        from pywinauto import keyboard

        # pywinauto uses {+} etc for special chars; send plain text via type_keys with pause
        keyboard.send_keys(text, with_spaces=True, pause=0.02)

    async def key(self, app: str, key: str) -> dict[str, Any]:
        info = await self._resolve_app(app)
        self._guard(app, bundle_id=info.bundle_id, name=info.name)
        await asyncio.to_thread(self._activate_sync, info)
        await asyncio.to_thread(self._key_sync, key)
        return {"ok": True, "action": "key", "app": info.app_id, "key": key}

    def _key_sync(self, key: str) -> None:
        from pywinauto import keyboard

        mapping = {
            "return": "{ENTER}",
            "enter": "{ENTER}",
            "tab": "{TAB}",
            "escape": "{ESC}",
            "delete": "{DELETE}",
            "backspace": "{BACKSPACE}",
            "space": " ",
            "up": "{UP}",
            "down": "{DOWN}",
            "left": "{LEFT}",
            "right": "{RIGHT}",
        }
        keyboard.send_keys(mapping.get(key.lower(), key), pause=0.02)

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
        from pywinauto import mouse

        # wheel distance: positive = up
        delta = amount if direction in ("up", "top") else -amount
        if direction in ("left", "right"):
            # horizontal not universally supported; approximate with vertical noop
            delta = amount if direction == "left" else -amount
        mouse.scroll(coords=None, wheel_dist=delta)
