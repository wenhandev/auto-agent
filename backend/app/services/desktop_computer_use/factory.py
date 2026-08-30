"""Resolve the desktop Computer Use backend for this runtime."""

from __future__ import annotations

import sys
from typing import Optional

from app.services.desktop_computer_use.protocol import (
    DesktopComputerUseBackend,
    DesktopComputerUseUnavailableError,
)

_INJECTED: Optional[DesktopComputerUseBackend] = None
_CACHED: Optional[DesktopComputerUseBackend] = None


def set_desktop_backend_for_tests(backend: Optional[DesktopComputerUseBackend]) -> None:
    """Inject a backend for tests. Always clears the process cache."""
    global _INJECTED, _CACHED
    _INJECTED = backend
    _CACHED = None


def reset_desktop_backend_for_tests() -> None:
    """Clear injection and process-scoped singleton (tests / recovery)."""
    global _INJECTED, _CACHED
    _INJECTED = None
    _CACHED = None


def _probe_platform_deps() -> tuple[bool, str]:
    if sys.platform == "darwin":
        try:
            import AppKit  # noqa: F401
            import ApplicationServices  # noqa: F401
            import Quartz  # noqa: F401
        except ImportError as exc:
            return (
                False,
                "macOS Computer Use requires pyobjc "
                f"(pip install -e '.[desktop-macos]'): {exc}",
            )
        return True, ""
    if sys.platform == "win32":
        try:
            import pywinauto  # noqa: F401
            from PIL import ImageGrab  # noqa: F401
        except ImportError as exc:
            return (
                False,
                "Windows Computer Use requires pywinauto and Pillow "
                f"(pip install -e '.[desktop-windows]'): {exc}",
            )
        return True, ""
    return False, "desktop Computer Use requires macOS or Windows"


def desktop_computer_use_availability() -> tuple[bool, str]:
    """Return (available, reason). reason is empty when available."""
    if _INJECTED is not None:
        return True, ""
    ok, reason = _probe_platform_deps()
    return ok, reason


def desktop_computer_use_available() -> bool:
    return desktop_computer_use_availability()[0]


def _construct_platform_backend() -> DesktopComputerUseBackend:
    if sys.platform == "darwin":
        try:
            from app.services.desktop_computer_use.macos import (
                MacOSDesktopComputerUseBackend,
            )
        except Exception as exc:  # pragma: no cover - import/env specific
            raise DesktopComputerUseUnavailableError(
                f"macOS Computer Use backend unavailable: {exc}"
            ) from exc
        return MacOSDesktopComputerUseBackend()
    if sys.platform == "win32":
        try:
            from app.services.desktop_computer_use.windows import (
                WindowsDesktopComputerUseBackend,
            )
        except Exception as exc:  # pragma: no cover - import/env specific
            raise DesktopComputerUseUnavailableError(
                f"Windows Computer Use backend unavailable: {exc}"
            ) from exc
        return WindowsDesktopComputerUseBackend()
    raise DesktopComputerUseUnavailableError(
        "desktop Computer Use requires macOS or Windows"
    )


def resolve_desktop_backend() -> DesktopComputerUseBackend:
    global _CACHED
    if _INJECTED is not None:
        return _INJECTED
    if _CACHED is not None:
        return _CACHED
    _CACHED = _construct_platform_backend()
    return _CACHED
