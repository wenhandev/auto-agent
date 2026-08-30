"""FakeDesktopComputerUseBackend round-trip tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.desktop_computer_use.auth import reset_auth_store_for_tests
from app.services.desktop_computer_use.factory import (
    desktop_computer_use_availability,
    desktop_computer_use_available,
    reset_desktop_backend_for_tests,
    resolve_desktop_backend,
    set_desktop_backend_for_tests,
)
from app.services.desktop_computer_use.fake import FakeDesktopComputerUseBackend
from app.services.desktop_computer_use.protocol import (
    DesktopAppAuthorizationError,
    DesktopAppForbiddenError,
    DesktopComputerUseUnavailableError,
)


@pytest.fixture
def auth(tmp_path: Path):
    store = reset_auth_store_for_tests(tmp_path / "auth.json")
    store.allow_always("com.apple.TextEdit")
    yield store
    set_desktop_backend_for_tests(None)
    if (tmp_path / "auth.json").exists():
        (tmp_path / "auth.json").unlink()


@pytest.fixture
def backend(auth) -> FakeDesktopComputerUseBackend:
    fake = FakeDesktopComputerUseBackend(auth=auth)
    set_desktop_backend_for_tests(fake)
    return fake


@pytest.mark.asyncio
async def test_get_app_state_and_type(backend: FakeDesktopComputerUseBackend) -> None:
    state = await backend.get_app_state("TextEdit")
    assert state.elements
    assert state.elements[0].role == "textfield"
    typed = await backend.type_text("TextEdit", "hello", index=0)
    assert typed["ok"] is True
    state2 = await backend.get_app_state("com.apple.TextEdit")
    assert "hello" in (state2.elements[0].value or "")


@pytest.mark.asyncio
async def test_click_by_index(backend: FakeDesktopComputerUseBackend) -> None:
    result = await backend.click("TextEdit", index=1)
    assert result["ok"] is True
    assert result["index"] == 1


@pytest.mark.asyncio
async def test_terminal_forbidden(auth) -> None:
    fake = FakeDesktopComputerUseBackend(
        auth=auth,
        apps={
            "com.apple.Terminal": {
                "name": "Terminal",
                "elements": [{"role": "textfield", "name": "term"}],
            }
        },
    )
    with pytest.raises(DesktopAppForbiddenError):
        await fake.get_app_state("Terminal")


@pytest.mark.asyncio
async def test_unapproved_blocked(tmp_path: Path) -> None:
    store = reset_auth_store_for_tests(tmp_path / "auth2.json")
    fake = FakeDesktopComputerUseBackend(auth=store)
    with pytest.raises(DesktopAppAuthorizationError):
        await fake.open_app("TextEdit")
    if (tmp_path / "auth2.json").exists():
        (tmp_path / "auth2.json").unlink()


def test_factory_uses_injected_backend(backend: FakeDesktopComputerUseBackend) -> None:
    assert desktop_computer_use_available() is True
    assert resolve_desktop_backend() is backend


def test_factory_linux_without_inject(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_desktop_backend_for_tests()
    monkeypatch.setattr("app.services.desktop_computer_use.factory.sys.platform", "linux")
    with pytest.raises(DesktopComputerUseUnavailableError, match="macOS or Windows"):
        resolve_desktop_backend()
    available, reason = desktop_computer_use_availability()
    assert available is False
    assert "macOS or Windows" in reason


def test_factory_win32_reuses_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_desktop_backend_for_tests()
    monkeypatch.setattr("app.services.desktop_computer_use.factory.sys.platform", "win32")

    instances: list[object] = []

    class _Stub:
        provider_id = "windows_foreground"

        def __init__(self) -> None:
            instances.append(self)

    import app.services.desktop_computer_use.windows as win_mod

    monkeypatch.setattr(win_mod, "WindowsDesktopComputerUseBackend", _Stub)
    monkeypatch.setattr(
        "app.services.desktop_computer_use.factory._probe_platform_deps",
        lambda: (True, ""),
    )
    first = resolve_desktop_backend()
    second = resolve_desktop_backend()
    assert first is second
    assert first.provider_id == "windows_foreground"
    assert len(instances) == 1
    reset_desktop_backend_for_tests()


@pytest.mark.asyncio
async def test_resolve_singleton_preserves_index_cache(
    monkeypatch: pytest.MonkeyPatch, auth
) -> None:
    """Without set_desktop_backend_for_tests, resolve must reuse instance so indices work."""
    reset_desktop_backend_for_tests()
    monkeypatch.setattr("app.services.desktop_computer_use.factory.sys.platform", "darwin")
    monkeypatch.setattr(
        "app.services.desktop_computer_use.factory._probe_platform_deps",
        lambda: (True, ""),
    )

    instances: list[FakeDesktopComputerUseBackend] = []

    class _FactoryFake(FakeDesktopComputerUseBackend):
        def __init__(self) -> None:
            super().__init__(auth=auth)
            instances.append(self)

    import app.services.desktop_computer_use.macos as mac_mod

    monkeypatch.setattr(mac_mod, "MacOSDesktopComputerUseBackend", _FactoryFake)

    backend_a = resolve_desktop_backend()
    backend_b = resolve_desktop_backend()
    assert backend_a is backend_b
    assert len(instances) == 1

    state = await backend_a.get_app_state("TextEdit")
    assert state.elements
    clicked = await backend_b.click("TextEdit", index=state.elements[0].index)
    assert clicked["ok"] is True
    reset_desktop_backend_for_tests()


def test_availability_false_when_deps_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_desktop_backend_for_tests()
    monkeypatch.setattr("app.services.desktop_computer_use.factory.sys.platform", "darwin")
    monkeypatch.setattr(
        "app.services.desktop_computer_use.factory._probe_platform_deps",
        lambda: (False, "macOS Computer Use requires pyobjc"),
    )
    assert desktop_computer_use_available() is False
    _, reason = desktop_computer_use_availability()
    assert "pyobjc" in reason
