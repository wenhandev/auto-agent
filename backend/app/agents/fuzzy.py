from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Awaitable, Callable, Literal

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools import FunctionTool
from google.genai import types

from app.agents.model import get_adk_model
from app.settings import settings
from app.tools import actions
from app.tools.browser import get_page


logger = logging.getLogger(__name__)

_APP_NAME = "auto-agent-fuzzy"

FUZZY_INSTRUCTION = """\
You are operating a browser. The page is ALREADY navigated to the target URL.
Do NOT navigate elsewhere unless the instruction explicitly asks. Use selectors
that exist on the CURRENT page, which you can see in the screenshot. If unsure,
scroll or take another screenshot before acting.

You can call these tools to interact with the currently-open page:

  - click_text(text): click the first element whose visible text matches.
  - click_selector(selector): click using a CSS / Playwright selector.
  - fill_field(selector, value): type `value` into the element.
  - scroll(direction, amount): scroll the page up/down by `amount` px.
  - screenshot(): take a screenshot of the page (returns status only).
  - done(summary): MUST be called exactly once when the task is finished.

Each tool result includes the page's current URL and title so you always know
where you are.

Rules:
  - Take at most a few steps. Be decisive.
  - When you have an answer or have completed the action, call `done(summary)`.
  - Keep the `summary` short and in the user's language.
"""


async def _page_context() -> dict:
    page = await get_page()
    try:
        title = await page.title()
    except Exception:
        title = ""
    return {"url": page.url, "title": title}


async def click_text(text: str) -> dict:
    page = await get_page()
    await page.get_by_text(text, exact=False).first.click()
    ctx = await _page_context()
    return {"clicked_text": text, **ctx}


async def click_selector(selector: str) -> dict:
    result = await actions.click(selector)
    ctx = await _page_context()
    return {**result, **ctx}


async def fill_field(selector: str, value: str) -> dict:
    result = await actions.fill(selector, value)
    ctx = await _page_context()
    return {**result, **ctx}


async def scroll(direction: Literal["up", "down"], amount: int = 500) -> dict:
    page = await get_page()
    dy = amount if direction == "down" else -amount
    await page.mouse.wheel(0, dy)
    ctx = await _page_context()
    return {"direction": direction, "amount": amount, **ctx}


async def screenshot() -> dict:
    await actions.screenshot()
    ctx = await _page_context()
    return {"status": "ok", **ctx}


async def done(summary: str) -> dict:
    return {"status": "done", "summary": summary}


def _truncate(value: Any, limit: int = 60) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


class FuzzyAgent:
    def _has_api_key(self) -> bool:
        provider = (settings.llm_provider or "openai").lower()
        if provider == "openai":
            return bool(settings.openai_api_key)
        if provider in ("google", "gemini"):
            return bool(settings.google_api_key)
        return False

    async def _run_keyless_stub(
        self, on_progress: Callable[[str], Awaitable[None]]
    ) -> dict:
        logger.warning(
            "FuzzyAgent: no LLM API key configured; emitting demo-mode stub"
        )
        for msg in ("分析页面截图...", "决定下一步动作...", "执行点击..."):
            await on_progress(msg)
            await asyncio.sleep(0.7)
        return {
            "completed": False,
            "reason": "no_api_key",
            "summary": "demo-mode stub (configure GOOGLE_API_KEY or OPENAI_API_KEY)",
        }

    async def _run_live(
        self,
        instruction: str,
        on_progress: Callable[[str], Awaitable[None]],
    ) -> dict:
        max_steps = max(1, settings.fuzzy_max_steps)
        state = {
            "n": 0,
            "done_summary": None,
            "stop": False,
            "last_observation": None,
        }

        async def before_tool_callback(tool, args, tool_context):  # type: ignore[no-untyped-def]
            name = getattr(tool, "name", getattr(tool, "__name__", "tool"))
            try:
                await on_progress(f"调用 {name}({_truncate(args)})")
            except Exception:
                pass
            state["n"] += 1
            if name == "done":
                state["done_summary"] = (
                    args.get("summary") if isinstance(args, dict) else None
                )
            if state["n"] > max_steps:
                state["stop"] = True
                return {"status": "max_steps_exceeded"}
            return None

        async def after_tool_callback(tool, args, tool_context, tool_response):  # type: ignore[no-untyped-def]
            try:
                state["last_observation"] = _truncate(tool_response, limit=200)
            except Exception:
                pass
            return None

        page = await get_page()
        prefixed_instruction = (
            f"Current URL: {page.url}\n"
            f"Current page title: {await page.title() if not page.is_closed() else ''}\n\n"
            f"Instruction: {instruction}"
        )

        agent = LlmAgent(
            name="fuzzy",
            model=get_adk_model(),
            instruction=FUZZY_INSTRUCTION,
            tools=[
                FunctionTool(click_text),
                FunctionTool(click_selector),
                FunctionTool(fill_field),
                FunctionTool(scroll),
                FunctionTool(screenshot),
                FunctionTool(done),
            ],
            before_tool_callback=before_tool_callback,
            after_tool_callback=after_tool_callback,
        )
        session_service = InMemorySessionService()
        runner = Runner(app_name=_APP_NAME, agent=agent, session_service=session_service)

        user_id = "fuzzy-user"
        session_id = f"fuzzy-{uuid.uuid4().hex[:12]}"
        await session_service.create_session(
            app_name=_APP_NAME, user_id=user_id, session_id=session_id
        )

        message = types.Content(
            role="user", parts=[types.Part(text=prefixed_instruction)]
        )
        async for event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=message
        ):
            if state["stop"]:
                break
            if state["done_summary"] is not None:
                break
            if event.is_final_response():
                break

        if state["done_summary"] is not None:
            return {
                "completed": True,
                "summary": state["done_summary"],
                "steps": state["n"],
            }
        return {
            "completed": False,
            "reason": "max_steps_reached",
            "steps": state["n"],
            "last_observation": state["last_observation"],
        }

    async def run_fuzzy_action(
        self,
        instruction: str,
        on_progress: Callable[[str], Awaitable[None]],
    ) -> dict:
        if not self._has_api_key():
            return await self._run_keyless_stub(on_progress)
        return await self._run_live(instruction, on_progress)
