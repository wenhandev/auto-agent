"""Self-healing selector finder agent.

Exposes ``propose_selector`` which asks the active LLM (via ADK ``LlmAgent``)
for a replacement selector. Two modes:

- ``mode="dom"``: text-only — the prompt receives the page's accessibility
  snapshot. Cheap. Tried first by the self-heal flow.
- ``mode="vision"``: same prompt PLUS a PNG screenshot attached as a content
  part. More expensive; only used when the DOM stage's confidence falls below
  the configured ``LlmConfig.self_healing_vision_threshold``.

The agent is constrained to call a single ``propose_selector`` tool exactly
once with ``selector`` / ``confidence`` / ``reasoning``. The tool body just
captures the args; the args become the function's return value. Each call is
wrapped in ``asyncio.wait_for(..., 15.0)`` so a hung LLM cannot pin the
executor for more than the per-stage budget.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Literal, Optional

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools import FunctionTool
from google.genai import types

from app.agents.model import get_adk_model


logger = logging.getLogger(__name__)

_APP_NAME = "auto-agent-selector-finder"
_STAGE_TIMEOUT_SECONDS = 15.0
_AX_SNAPSHOT_LIMIT = 6_000

SELECTOR_FINDER_INSTRUCTION = """\
You repair broken Playwright selectors. The original selector below failed to
match any element on the current page. Pick a SINGLE replacement selector for
the SAME logical element the user intends to act on.

You MUST call the tool `propose_selector` EXACTLY ONCE with:
  - selector: a CSS, attribute, or text-based Playwright selector that you
    believe identifies the intended element. Prefer stable attributes
    (data-testid, id, name) over class chains. Prefer text-based selectors
    (`text="..."` / `:has-text("...")`) when the visible label is unique.
  - confidence: a float in [0.0, 1.0]. Use >=0.7 only when you are confident
    the candidate is unambiguously the same element; use <0.5 when you are
    guessing because the page does not contain enough signal.
  - reasoning: one short sentence explaining your pick.

Do NOT call the tool more than once. Do NOT reply with prose; the only valid
response is the tool call.
"""


def _truncate_ax(text: str) -> str:
    if len(text) <= _AX_SNAPSHOT_LIMIT:
        return text
    return text[:_AX_SNAPSHOT_LIMIT] + "\n…[truncated]"


async def _accessibility_text(page: Any) -> str:
    try:
        snapshot = await page.accessibility.snapshot()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("selector_finder: ax snapshot failed (%s)", exc)
        snapshot = None
    if snapshot:
        try:
            return _truncate_ax(
                json.dumps(snapshot, ensure_ascii=False, default=str)
            )
        except Exception:
            pass
    try:
        text = await page.locator("body").inner_text()
    except Exception:
        text = ""
    return _truncate_ax(text.strip())


async def _grab_screenshot(page: Any) -> Optional[bytes]:
    try:
        password_locator = page.locator('input[type="password"]')
        return await page.screenshot(
            full_page=False, type="png", mask=[password_locator]
        )
    except Exception:
        try:
            return await page.screenshot(full_page=False, type="png")
        except Exception as exc:
            logger.warning("selector_finder: screenshot failed (%s)", exc)
            return None


def _build_prompt(*, instruction: str, ax_text: str) -> str:
    return (
        f"{instruction}\n\n"
        f"Accessibility snapshot of the CURRENT page:\n```\n{ax_text}\n```\n\n"
        "Use the snapshot (and the screenshot if provided) to propose the "
        "best replacement selector via the tool."
    )


def _empty_cost_hint(mode: str) -> dict:
    return {
        "input_tokens": None,
        "output_tokens": None,
        "vision_calls": 1 if mode == "vision" else 0,
    }


def _failure_result(*, mode: str, reasoning: str) -> dict:
    return {
        "selector": None,
        "confidence": 0.0,
        "reasoning": reasoning,
        "cost_hint": _empty_cost_hint(mode),
    }


async def _run_agent(
    *,
    mode: Literal["dom", "vision"],
    user_prompt: str,
    screenshot: Optional[bytes],
) -> dict:
    captured: dict[str, Any] = {}

    async def propose_selector(
        selector: str, confidence: float, reasoning: str
    ) -> dict:
        captured["selector"] = str(selector)
        try:
            captured["confidence"] = float(confidence)
        except Exception:
            captured["confidence"] = 0.0
        captured["reasoning"] = str(reasoning)
        return {"ok": True}

    try:
        model = get_adk_model()
    except Exception as exc:
        logger.warning("selector_finder: get_adk_model failed (%s)", exc)
        return _failure_result(mode=mode, reasoning=f"agent unavailable: {exc}")

    agent = LlmAgent(
        name="selector_finder",
        model=model,
        instruction=SELECTOR_FINDER_INSTRUCTION,
        tools=[FunctionTool(propose_selector)],
    )
    session_service = InMemorySessionService()
    runner = Runner(
        app_name=_APP_NAME, agent=agent, session_service=session_service
    )

    user_id = "self-heal-user"
    session_id = f"self-heal-{uuid.uuid4().hex[:12]}"
    await session_service.create_session(
        app_name=_APP_NAME, user_id=user_id, session_id=session_id
    )

    parts: list[Any] = []
    if mode == "vision" and screenshot is not None:
        parts.append(
            types.Part.from_bytes(data=screenshot, mime_type="image/png")
        )
    parts.append(types.Part(text=user_prompt))
    message = types.Content(role="user", parts=parts)

    usage = {"input_tokens": None, "output_tokens": None}

    try:
        async for event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=message
        ):
            meta = getattr(event, "usage_metadata", None)
            if meta is not None:
                pt = getattr(meta, "prompt_token_count", None)
                ct = getattr(meta, "candidates_token_count", None)
                if isinstance(pt, int):
                    usage["input_tokens"] = (usage["input_tokens"] or 0) + pt
                if isinstance(ct, int):
                    usage["output_tokens"] = (usage["output_tokens"] or 0) + ct
            if captured.get("selector") and event.is_final_response():
                break
            if event.is_final_response():
                break
    except Exception as exc:
        logger.warning("selector_finder: runner failed (%s)", exc)
        return _failure_result(
            mode=mode, reasoning=f"agent error: {exc}"
        )

    cost_hint = {
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "vision_calls": 1 if mode == "vision" else 0,
    }

    if not captured.get("selector"):
        return {
            "selector": None,
            "confidence": float(captured.get("confidence", 0.0)),
            "reasoning": captured.get("reasoning", "no_candidate"),
            "cost_hint": cost_hint,
        }
    return {
        "selector": captured["selector"],
        "confidence": float(captured.get("confidence", 0.0)),
        "reasoning": captured.get("reasoning", ""),
        "cost_hint": cost_hint,
    }


async def propose_selector(
    *,
    page: Any,
    instruction: str,
    mode: Literal["dom", "vision"],
) -> dict:
    """Ask the active LLM for a replacement selector.

    Returns a dict with ``selector`` (str|None), ``confidence`` (float),
    ``reasoning`` (str), and ``cost_hint`` (dict with input_tokens,
    output_tokens, vision_calls). On timeout the call returns
    ``{selector: None, confidence: 0.0, reasoning: "timeout", ...}`` rather
    than raising so the caller can move to the next stage.
    """
    ax_text = await _accessibility_text(page)
    user_prompt = _build_prompt(instruction=instruction, ax_text=ax_text)
    screenshot = None
    if mode == "vision":
        screenshot = await _grab_screenshot(page)

    try:
        return await asyncio.wait_for(
            _run_agent(mode=mode, user_prompt=user_prompt, screenshot=screenshot),
            timeout=_STAGE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("selector_finder: stage %s timed out after 15s", mode)
        return _failure_result(mode=mode, reasoning="timeout")


__all__ = ["propose_selector", "SELECTOR_FINDER_INSTRUCTION"]
