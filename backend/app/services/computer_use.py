"""Provider-neutral Computer Use fallback controller."""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.agents.autonomous_guardrails import check_navigation
from app.services import artifact_context
from app.settings import settings


EmitFn = Callable[[dict[str, Any]], Any]
PageProvider = Callable[[], Awaitable[Any]]
ConfirmationHandler = Callable[[str, dict[str, Any]], Awaitable[bool]]

_ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / ".vision_artifacts"


class ComputerUseUnavailableError(Exception):
    """Raised when Computer Use fallback is requested but unavailable."""


class ComputerUseAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    args: dict[str, Any] = Field(default_factory=dict)
    destructive: bool = False


class ComputerUseController(Protocol):
    provider_id: str

    async def screenshot(self, page: Any) -> dict[str, Any]: ...

    async def click_at(self, page: Any, action: ComputerUseAction) -> dict[str, Any]: ...

    async def type_text(self, page: Any, action: ComputerUseAction) -> dict[str, Any]: ...

    async def scroll(self, page: Any, action: ComputerUseAction) -> dict[str, Any]: ...

    async def keypress(self, page: Any, action: ComputerUseAction) -> dict[str, Any]: ...

    async def drag(self, page: Any, action: ComputerUseAction) -> dict[str, Any]: ...

    async def wait(self, page: Any, action: ComputerUseAction) -> dict[str, Any]: ...

    async def navigate(self, page: Any, action: ComputerUseAction) -> dict[str, Any]: ...


def computer_use_enabled() -> bool:
    return bool(settings.computer_use_enabled)


def resolve_computer_use_controller() -> ComputerUseController:
    if not computer_use_enabled():
        raise ComputerUseUnavailableError("computer use fallback is disabled")
    provider = (settings.computer_use_provider or "").strip().lower()
    if provider == "local_playwright":
        return LocalPlaywrightComputerUseController()
    raise ComputerUseUnavailableError(
        f"computer use provider {settings.computer_use_provider!r} is unavailable"
    )


def should_attempt_computer_use_fallback(structured_result: dict[str, Any]) -> bool:
    return bool(structured_result.get("error"))


def _store_screenshot(data: bytes) -> str:
    run_id = artifact_context.get_run_id()
    if run_id:
        from app.services import artifacts as artifact_svc

        row = artifact_svc.store_screenshot(
            run_id,
            data,
            step_index=artifact_context.get_step_index(),
            node_id=artifact_context.get_node_id(),
        )
        return str(artifact_svc.resolve_path(row))

    _ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    path = _ARTIFACT_ROOT / f"computer-use-{uuid.uuid4().hex[:12]}.png"
    path.write_bytes(data)
    return str(path)


@dataclass
class LocalPlaywrightComputerUseController:
    provider_id: str = "local_playwright"

    async def screenshot(self, page: Any) -> dict[str, Any]:
        data = await page.screenshot(full_page=False, type="png")
        screenshot_ref = _store_screenshot(data)
        return {
            "provider": self.provider_id,
            "action": "screenshot",
            "url": getattr(page, "url", ""),
            "screenshot_ref": screenshot_ref,
        }

    async def click_at(self, page: Any, action: ComputerUseAction) -> dict[str, Any]:
        x = int(action.args["x"])
        y = int(action.args["y"])
        await page.mouse.click(x, y)
        screenshot = await self.screenshot(page)
        return {
            "provider": self.provider_id,
            "action": "click_at",
            "coordinates": {"x": x, "y": y},
            "url": getattr(page, "url", ""),
            "screenshot_ref": screenshot["screenshot_ref"],
        }

    async def type_text(self, page: Any, action: ComputerUseAction) -> dict[str, Any]:
        text = str(action.args.get("text", ""))
        x = action.args.get("x")
        y = action.args.get("y")
        if x is not None and y is not None:
            await page.mouse.click(int(x), int(y))
        await page.keyboard.type(text)
        screenshot = await self.screenshot(page)
        return {
            "provider": self.provider_id,
            "action": "type_text",
            "text": text,
            "coordinates": {"x": x, "y": y} if x is not None and y is not None else None,
            "url": getattr(page, "url", ""),
            "screenshot_ref": screenshot["screenshot_ref"],
        }

    async def scroll(self, page: Any, action: ComputerUseAction) -> dict[str, Any]:
        direction = str(action.args.get("direction", "down"))
        amount = int(action.args.get("amount", 500))
        dy = amount if direction == "down" else -amount
        await page.mouse.wheel(0, dy)
        screenshot = await self.screenshot(page)
        return {
            "provider": self.provider_id,
            "action": "scroll",
            "direction": direction,
            "amount": amount,
            "url": getattr(page, "url", ""),
            "screenshot_ref": screenshot["screenshot_ref"],
        }

    async def keypress(self, page: Any, action: ComputerUseAction) -> dict[str, Any]:
        key = str(action.args.get("key", "Enter"))
        await page.keyboard.press(key)
        screenshot = await self.screenshot(page)
        return {
            "provider": self.provider_id,
            "action": "keypress",
            "key": key,
            "url": getattr(page, "url", ""),
            "screenshot_ref": screenshot["screenshot_ref"],
        }

    async def drag(self, page: Any, action: ComputerUseAction) -> dict[str, Any]:
        from_x = int(action.args["from_x"])
        from_y = int(action.args["from_y"])
        to_x = int(action.args["to_x"])
        to_y = int(action.args["to_y"])
        await page.mouse.move(from_x, from_y)
        await page.mouse.down()
        await page.mouse.move(to_x, to_y)
        await page.mouse.up()
        screenshot = await self.screenshot(page)
        return {
            "provider": self.provider_id,
            "action": "drag",
            "coordinates": {
                "from_x": from_x,
                "from_y": from_y,
                "to_x": to_x,
                "to_y": to_y,
            },
            "url": getattr(page, "url", ""),
            "screenshot_ref": screenshot["screenshot_ref"],
        }

    async def wait(self, page: Any, action: ComputerUseAction) -> dict[str, Any]:
        import asyncio

        ms = int(action.args.get("ms", 500))
        await asyncio.sleep(max(0, ms) / 1000)
        screenshot = await self.screenshot(page)
        return {
            "provider": self.provider_id,
            "action": "wait",
            "waited_ms": ms,
            "url": getattr(page, "url", ""),
            "screenshot_ref": screenshot["screenshot_ref"],
        }

    async def navigate(self, page: Any, action: ComputerUseAction) -> dict[str, Any]:
        url = str(action.args.get("url", ""))
        await page.goto(url)
        screenshot = await self.screenshot(page)
        return {
            "provider": self.provider_id,
            "action": "navigate",
            "url": getattr(page, "url", url),
            "screenshot_ref": screenshot["screenshot_ref"],
        }


async def _maybe_emit(emit: Optional[EmitFn], payload: dict[str, Any]) -> None:
    if emit is None:
        return
    result = emit(payload)
    if inspect.isawaitable(result):
        await result


class ComputerUseRuntime:
    def __init__(
        self,
        *,
        page_provider: PageProvider,
        controller_factory: Callable[[], ComputerUseController] = resolve_computer_use_controller,
        confirmation_handler: Optional[ConfirmationHandler] = None,
    ) -> None:
        self._page_provider = page_provider
        self._controller_factory = controller_factory
        self._confirmation_handler = confirmation_handler

    async def execute(
        self,
        action: ComputerUseAction,
        *,
        reason: str,
        allowed_domains: Optional[list[str]],
        require_confirmation: bool,
        destructive: bool = False,
        emit: Optional[EmitFn] = None,
    ) -> dict[str, Any]:
        if action.action == "navigate":
            url = str(action.args.get("url", ""))
            nav_err = check_navigation(url, allowed_domains)
            if nav_err:
                return {"error": nav_err}

        if require_confirmation and (destructive or action.destructive):
            handler = self._confirmation_handler
            if handler is None:
                from app.agents.autonomous_guardrails import default_confirmation_handler

                handler = default_confirmation_handler
            approved = await handler(
                f"computer_use:{action.action}",
                action.model_dump(),
            )
            if not approved:
                return {"error": "confirmation_required"}

        try:
            controller = self._controller_factory()
        except ComputerUseUnavailableError as exc:
            return {"error": str(exc)}

        page = await self._page_provider()
        dispatch = {
            "screenshot": lambda: controller.screenshot(page),
            "click_at": lambda: controller.click_at(page, action),
            "type_text": lambda: controller.type_text(page, action),
            "scroll": lambda: controller.scroll(page, action),
            "keypress": lambda: controller.keypress(page, action),
            "drag": lambda: controller.drag(page, action),
            "wait": lambda: controller.wait(page, action),
            "navigate": lambda: controller.navigate(page, action),
        }
        handler = dispatch.get(action.action)
        if handler is None:
            return {"error": f"unsupported computer use action {action.action!r}"}

        result = await handler()
        payload = {
            "event": "computer_use_action",
            "provider": result.get("provider", controller.provider_id),
            "reason": reason,
            "action": action.action,
            "payload": dict(action.args),
            "coordinates": result.get("coordinates"),
            "result": result,
            "url": result.get("url", getattr(page, "url", "")),
            "screenshot_ref": result.get("screenshot_ref"),
        }
        await _maybe_emit(emit, payload)
        return result


__all__ = [
    "ComputerUseAction",
    "ComputerUseController",
    "ComputerUseRuntime",
    "ComputerUseUnavailableError",
    "LocalPlaywrightComputerUseController",
    "computer_use_enabled",
    "resolve_computer_use_controller",
    "should_attempt_computer_use_fallback",
]
