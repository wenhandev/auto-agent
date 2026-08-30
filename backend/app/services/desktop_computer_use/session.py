"""Interactive desktop session checks (screen lock / no input desktop)."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Optional

SessionChecker = Callable[[], Optional[str]]

_INJECTED: Optional[SessionChecker] = None


class DesktopSessionUnavailableError(Exception):
    """Raised when the OS session cannot accept GUI input."""


def set_session_checker_for_tests(checker: Optional[SessionChecker]) -> None:
    global _INJECTED
    _INJECTED = checker


def check_interactive_session() -> Optional[str]:
    """Return a diagnostic error string if GUI input is unavailable, else None."""
    if _INJECTED is not None:
        return _INJECTED()
    if sys.platform == "darwin":
        return _check_macos_locked()
    if sys.platform == "win32":
        return _check_windows_session()
    return None


def require_interactive_session() -> None:
    err = check_interactive_session()
    if err:
        raise DesktopSessionUnavailableError(err)


def _check_macos_locked() -> Optional[str]:
    try:
        import Quartz  # type: ignore

        session = Quartz.CGSessionCopyCurrentDictionary()
        if not session:
            return None
        # CFDictionary bridging may expose keys as str
        locked = session.get("CGSSessionScreenIsLocked") or session.get(
            "kCGSSessionOnConsoleKey"
        )
        # CGSSessionScreenIsLocked == 1 means locked
        if session.get("CGSSessionScreenIsLocked") in (1, True, "1"):
            return (
                "macOS screen is locked; unlock the session to continue "
                "Computer Use"
            )
        # If not on console, GUI may be unavailable
        on_console = session.get("kCGSSessionOnConsoleKey")
        if on_console is False or on_console == 0:
            return "macOS session is not on the active console"
        _ = locked
    except Exception:
        return None
    return None


def _check_windows_session() -> Optional[str]:
    try:
        import ctypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        DESKTOP_READOBJECTS = 0x0001
        hdesk = user32.OpenInputDesktop(0, False, DESKTOP_READOBJECTS)
        if not hdesk:
            return (
                "Windows session has no interactive desktop "
                "(locked or disconnected?)"
            )
        user32.CloseDesktop(hdesk)
    except Exception:
        return None
    return None
