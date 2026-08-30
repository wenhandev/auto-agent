"""Desktop Computer Use app auth + forbidden list tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.desktop_computer_use.auth import (
    DesktopAppAuthStore,
    reset_auth_store_for_tests,
)
from app.services.desktop_computer_use.forbidden import is_forbidden_app
from app.services.desktop_computer_use.protocol import (
    DesktopAppAuthorizationError,
    DesktopAppForbiddenError,
)


@pytest.fixture
def auth_store(tmp_path: Path) -> DesktopAppAuthStore:
    path = tmp_path / "auth.json"
    store = reset_auth_store_for_tests(path)
    yield store
    # teardown: remove file
    if path.exists():
        path.unlink()
    reset_auth_store_for_tests(tmp_path / "auth-reset-empty.json")


def test_terminal_is_forbidden() -> None:
    assert is_forbidden_app("Terminal")
    assert is_forbidden_app("com.apple.Terminal")
    assert is_forbidden_app("iTerm")
    assert is_forbidden_app("cmd.exe")
    assert is_forbidden_app("powershell.exe")
    assert is_forbidden_app("WindowsTerminal.exe")


def test_textedit_not_forbidden() -> None:
    assert not is_forbidden_app("com.apple.TextEdit", name="TextEdit")


def test_unapproved_app_raises(auth_store: DesktopAppAuthStore) -> None:
    with pytest.raises(DesktopAppAuthorizationError, match="not authorized"):
        auth_store.require_authorized("com.apple.TextEdit")


def test_allow_always_persists(auth_store: DesktopAppAuthStore, tmp_path: Path) -> None:
    auth_store.allow_always("com.apple.TextEdit")
    assert auth_store.is_authorized("com.apple.TextEdit")
    # Reload from disk
    reloaded = DesktopAppAuthStore(path=tmp_path / "auth.json")
    assert reloaded.is_authorized("com.apple.TextEdit")
    assert "com.apple.TextEdit".lower() in [a.lower() for a in reloaded.list_always_allowed()]


def test_allow_once_not_persisted(auth_store: DesktopAppAuthStore, tmp_path: Path) -> None:
    auth_store.allow_once("com.apple.TextEdit")
    assert auth_store.is_authorized("com.apple.TextEdit")
    reloaded = DesktopAppAuthStore(path=tmp_path / "auth.json")
    assert not reloaded.is_authorized("com.apple.TextEdit")


def test_cannot_always_allow_forbidden(auth_store: DesktopAppAuthStore) -> None:
    with pytest.raises(DesktopAppAuthorizationError, match="hard-denied"):
        auth_store.allow_always("com.apple.Terminal")


def test_forbidden_require_raises_forbidden(auth_store: DesktopAppAuthStore) -> None:
    auth_store.allow_always("com.apple.TextEdit")
    with pytest.raises(DesktopAppForbiddenError):
        auth_store.require_authorized("Terminal")
