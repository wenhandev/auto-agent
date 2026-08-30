"""Native desktop Computer Use (macOS AX + screenshot)."""

from app.services.desktop_computer_use.app_lock import (
    DesktopAppBusyError,
    hold_desktop_app,
    reset_app_locks_for_tests,
)
from app.services.desktop_computer_use.auth import (
    DesktopAppAuthStore,
    get_auth_store,
    reset_auth_store_for_tests,
)
from app.services.desktop_computer_use.factory import (
    desktop_computer_use_availability,
    desktop_computer_use_available,
    reset_desktop_backend_for_tests,
    resolve_desktop_backend,
    set_desktop_backend_for_tests,
)
from app.services.desktop_computer_use.forbidden import is_forbidden_app
from app.services.desktop_computer_use.protocol import (
    DesktopAppAuthorizationError,
    DesktopAppForbiddenError,
    DesktopAppInfo,
    DesktopAppState,
    DesktopComputerUseBackend,
    DesktopComputerUseUnavailableError,
    DesktopElement,
)
from app.services.desktop_computer_use.session import (
    DesktopSessionUnavailableError,
    check_interactive_session,
    require_interactive_session,
    set_session_checker_for_tests,
)

__all__ = [
    "DesktopAppAuthStore",
    "DesktopAppAuthorizationError",
    "DesktopAppBusyError",
    "DesktopAppForbiddenError",
    "DesktopAppInfo",
    "DesktopAppState",
    "DesktopComputerUseBackend",
    "DesktopComputerUseUnavailableError",
    "DesktopElement",
    "DesktopSessionUnavailableError",
    "check_interactive_session",
    "desktop_computer_use_availability",
    "desktop_computer_use_available",
    "get_auth_store",
    "hold_desktop_app",
    "is_forbidden_app",
    "require_interactive_session",
    "reset_app_locks_for_tests",
    "reset_auth_store_for_tests",
    "reset_desktop_backend_for_tests",
    "resolve_desktop_backend",
    "set_desktop_backend_for_tests",
    "set_session_checker_for_tests",
]
