"""Windows launch helper tests (no pywinauto required)."""

from __future__ import annotations

import pytest

from app.services.desktop_computer_use.protocol import DesktopComputerUseUnavailableError
from app.services.desktop_computer_use.windows import launch_windows_app_controlled


def test_launch_windows_app_controlled_uses_cmd_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def _fake_popen(args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append({"args": args, "kwargs": kwargs})
        return object()

    monkeypatch.setattr(
        "app.services.desktop_computer_use.windows.subprocess.Popen",
        _fake_popen,
    )
    launch_windows_app_controlled("notepad.exe")
    assert len(calls) == 1
    assert calls[0]["args"] == ["cmd", "/c", "start", "", "notepad.exe"]
    assert calls[0]["kwargs"].get("shell") is False


def test_launch_windows_app_controlled_no_shell_true_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_a, **_k):  # type: ignore[no-untyped-def]
        raise OSError("start failed")

    monkeypatch.setattr(
        "app.services.desktop_computer_use.windows.subprocess.Popen",
        _boom,
    )
    with pytest.raises(DesktopComputerUseUnavailableError, match="controlled launch"):
        launch_windows_app_controlled("notepad.exe")


def test_launch_windows_app_controlled_rejects_empty() -> None:
    with pytest.raises(DesktopComputerUseUnavailableError, match="empty"):
        launch_windows_app_controlled("  ")
