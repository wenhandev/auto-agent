"""Computer Use fallback controller tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.computer_use import (
    ComputerUseAction,
    ComputerUseUnavailableError,
    LocalPlaywrightComputerUseController,
    computer_use_enabled,
    resolve_computer_use_controller,
    should_attempt_computer_use_fallback,
)


@pytest.fixture
def mock_page() -> MagicMock:
    page = MagicMock()
    page.url = "https://example.com/app"
    page.screenshot = AsyncMock(return_value=b"png-bytes")
    page.mouse = MagicMock()
    page.mouse.click = AsyncMock()
    page.mouse.wheel = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.type = AsyncMock()
    page.keyboard.press = AsyncMock()
    page.goto = AsyncMock()
    return page


def test_computer_use_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.settings import settings

    monkeypatch.setattr(settings, "computer_use_enabled", False)
    assert computer_use_enabled() is False
    with pytest.raises(ComputerUseUnavailableError, match="disabled"):
        resolve_computer_use_controller()


def test_unknown_provider_reports_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.settings import settings

    monkeypatch.setattr(settings, "computer_use_enabled", True)
    monkeypatch.setattr(settings, "computer_use_provider", "unknown")
    with pytest.raises(ComputerUseUnavailableError, match="provider"):
        resolve_computer_use_controller()


def test_should_not_fallback_when_structured_action_succeeds() -> None:
    assert should_attempt_computer_use_fallback({"clicked_index": 0}) is False


def test_should_fallback_when_structured_action_fails() -> None:
    assert should_attempt_computer_use_fallback({"error": "index unavailable"}) is True


@pytest.mark.asyncio
async def test_local_controller_click_at(mock_page: MagicMock) -> None:
    controller = LocalPlaywrightComputerUseController()
    result = await controller.click_at(
        mock_page,
        ComputerUseAction(action="click_at", args={"x": 120, "y": 340}),
    )

    assert result["provider"] == "local_playwright"
    assert result["action"] == "click_at"
    assert result["coordinates"] == {"x": 120, "y": 340}
    assert result["url"] == "https://example.com/app"
    mock_page.mouse.click.assert_awaited_once_with(120, 340)


@pytest.mark.asyncio
async def test_execute_records_audit_event(
    mock_page: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.settings import settings
    from app.services.computer_use import ComputerUseRuntime

    monkeypatch.setattr(settings, "computer_use_enabled", True)
    monkeypatch.setattr(settings, "computer_use_provider", "local_playwright")

    events: list[dict[str, Any]] = []
    runtime = ComputerUseRuntime(page_provider=AsyncMock(return_value=mock_page))

    result = await runtime.execute(
        ComputerUseAction(action="click_at", args={"x": 10, "y": 20}),
        reason="structured_action_failed",
        allowed_domains=None,
        require_confirmation=False,
        emit=events.append,
    )

    assert result["coordinates"] == {"x": 10, "y": 20}
    assert events == [
        {
            "event": "computer_use_action",
            "provider": "local_playwright",
            "reason": "structured_action_failed",
            "action": "click_at",
            "payload": {"x": 10, "y": 20},
            "coordinates": {"x": 10, "y": 20},
            "result": result,
            "url": "https://example.com/app",
            "screenshot_ref": result["screenshot_ref"],
        }
    ]


@pytest.mark.asyncio
async def test_execute_blocks_disallowed_domain_navigation(
    mock_page: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.settings import settings
    from app.services.computer_use import ComputerUseRuntime

    monkeypatch.setattr(settings, "computer_use_enabled", True)
    monkeypatch.setattr(settings, "computer_use_provider", "local_playwright")

    runtime = ComputerUseRuntime(page_provider=AsyncMock(return_value=mock_page))
    result = await runtime.execute(
        ComputerUseAction(action="navigate", args={"url": "https://evil.test/page"}),
        reason="structured_action_failed",
        allowed_domains=["example.com"],
        require_confirmation=False,
    )

    assert result["error"] == "navigation to evil.test blocked (not in allowed_domains)"
    mock_page.goto.assert_not_called()


@pytest.mark.asyncio
async def test_execute_respects_confirmation_gate(
    mock_page: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.settings import settings
    from app.services.computer_use import ComputerUseRuntime

    monkeypatch.setattr(settings, "computer_use_enabled", True)
    monkeypatch.setattr(settings, "computer_use_provider", "local_playwright")

    runtime = ComputerUseRuntime(
        page_provider=AsyncMock(return_value=mock_page),
        confirmation_handler=AsyncMock(return_value=False),
    )
    result = await runtime.execute(
        ComputerUseAction(action="click_at", args={"x": 50, "y": 50}),
        reason="canvas_only_ui",
        allowed_domains=None,
        require_confirmation=True,
        destructive=True,
    )

    assert result["error"] == "confirmation_required"
    mock_page.mouse.click.assert_not_awaited()


@pytest.mark.asyncio
async def test_primitive_act_uses_computer_use_when_structured_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.browser_primitives import (
        ActRequest,
        BrowserPrimitiveService,
        PrimitiveAction,
    )
    from app.services.perception import ElementSignature, IndexedElement, Observation

    observation = Observation(
        url="https://example.com",
        title="App",
        screenshot_bytes=b"png",
        screenshot_ref="/tmp/fake.png",
        ax_snapshot={},
        elements=[
            IndexedElement(
                index=0,
                role="button",
                name="Go",
                signature=ElementSignature(role="button", name="Go"),
            )
        ],
        page_text_summary="go",
    )

    async def failing_executor(action: PrimitiveAction, _observation: Observation) -> dict[str, Any]:
        return {"error": "element unavailable"}

    async def fake_fallback(_request, _observation, _result):
        return ComputerUseAction(action="click_at", args={"x": 11, "y": 22})

    async def fake_computer_use_execute(**kwargs):
        return {
            "provider": "local_playwright",
            "action": "click_at",
            "coordinates": {"x": 11, "y": 22},
            "url": "https://example.com",
            "screenshot_ref": "/tmp/cu.png",
        }

    service = BrowserPrimitiveService(
        page_provider=AsyncMock(return_value=MagicMock()),
        perceive_fn=AsyncMock(return_value=observation),
        action_resolver=AsyncMock(
            return_value=PrimitiveAction(name="click_element", args={"index": 0})
        ),
        action_executor=failing_executor,
        computer_use_fallback=fake_fallback,
        computer_use_execute=fake_computer_use_execute,
    )

    monkeypatch.setattr(
        "app.services.browser_primitives.computer_use_enabled",
        lambda: True,
    )

    result = await service.act(ActRequest(instruction="click canvas button"))

    assert result.source == "computer_use"
    assert result.result["coordinates"] == {"x": 11, "y": 22}
