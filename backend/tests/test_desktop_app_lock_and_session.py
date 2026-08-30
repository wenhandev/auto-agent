"""Desktop app lock + session gate tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.desktop import DesktopAgent
from app.agents.autonomous_guardrails import ConfirmationGate, is_destructive_action
from app.services.desktop_computer_use.app_lock import (
    DesktopAppBusyError,
    hold_desktop_app,
    reset_app_locks_for_tests,
)
from app.services.desktop_computer_use.auth import reset_auth_store_for_tests
from app.services.desktop_computer_use.factory import set_desktop_backend_for_tests
from app.services.desktop_computer_use.fake import FakeDesktopComputerUseBackend
from app.services.desktop_computer_use.session import (
    DesktopSessionUnavailableError,
    require_interactive_session,
    set_session_checker_for_tests,
)
from app.services.perception import (
    ElementSignature,
    IndexedElement,
    Observation,
)


@pytest.fixture(autouse=True)
def _clean_locks_and_session():
    reset_app_locks_for_tests()
    set_session_checker_for_tests(lambda: None)
    yield
    reset_app_locks_for_tests()
    set_session_checker_for_tests(None)
    set_desktop_backend_for_tests(None)


@pytest.fixture
def backend(tmp_path: Path) -> FakeDesktopComputerUseBackend:
    store = reset_auth_store_for_tests(tmp_path / "auth.json")
    store.allow_always("com.apple.TextEdit")
    fake = FakeDesktopComputerUseBackend(auth=store)
    set_desktop_backend_for_tests(fake)
    yield fake
    if (tmp_path / "auth.json").exists():
        (tmp_path / "auth.json").unlink()


def test_same_app_second_holder_busy() -> None:
    with hold_desktop_app("TextEdit", "run-a"):
        with pytest.raises(DesktopAppBusyError, match="already active"):
            with hold_desktop_app("TextEdit", "run-b"):
                pass


def test_same_holder_reentrant() -> None:
    with hold_desktop_app("TextEdit", "run-a"):
        with hold_desktop_app("TextEdit", "run-a"):
            pass


def test_locked_session_raises() -> None:
    set_session_checker_for_tests(lambda: "screen is locked")
    with pytest.raises(DesktopSessionUnavailableError, match="locked"):
        require_interactive_session()


@pytest.mark.asyncio
async def test_agent_respects_session_lock(
    backend: FakeDesktopComputerUseBackend,
) -> None:
    set_session_checker_for_tests(lambda: "screen is locked")
    agent = DesktopAgent(backend=backend)
    with pytest.raises(DesktopSessionUnavailableError):
        await agent.run_act("TextEdit", "type hello")


@pytest.mark.asyncio
async def test_agent_busy_when_other_holder(
    backend: FakeDesktopComputerUseBackend,
) -> None:
    agent = DesktopAgent(backend=backend)
    with hold_desktop_app("TextEdit", "other-run"):
        with pytest.raises(DesktopAppBusyError):
            await agent.run_act("TextEdit", "type hello", holder_id="this-run")


def test_desktop_type_payment_is_destructive() -> None:
    assert is_destructive_action(
        "desktop_type",
        {"app": "Notes", "text": "请完成支付确认"},
    )


def test_desktop_click_buy_button_destructive() -> None:
    obs = Observation(
        url="desktop://notes",
        title="Notes",
        screenshot_bytes=b"",
        screenshot_ref="r",
        ax_snapshot={},
        elements=[
            IndexedElement(
                index=0,
                role="button",
                name="Buy Now",
                signature=ElementSignature(role="button", name="Buy Now"),
            )
        ],
    )
    assert is_destructive_action("desktop_click", {"index": 0}, observation=obs)


@pytest.mark.asyncio
async def test_desktop_confirmation_gate_rejects() -> None:
    async def reject(_desc: str, _action: dict) -> bool:
        return False

    gate = ConfirmationGate(True, handler=reject)
    allowed, reason = await gate.check(
        "desktop_type",
        {"app": "Mail", "text": "send message to boss"},
    )
    assert allowed is False
    assert reason is not None
