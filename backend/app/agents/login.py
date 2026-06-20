"""Vision-driven login agent with server-side credential filling."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Awaitable, Callable, Literal, Optional

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools import FunctionTool
from google.genai import types

from app.agents.model import get_adk_model
from app.agents.vision import VisionStepCallback, _truncate
from app.services.perception import (
    Observation,
    format_elements_for_prompt,
    perceive,
    resolve_element,
)
from app.services.totp import TotpNotAvailable, resolve_totp_code
from app.settings import llm_is_configured, settings
from app.tools.browser import get_page


logger = logging.getLogger(__name__)

_APP_NAME = "auto-agent-login"

ProgressCallback = Callable[[str], Awaitable[None]]

LOGIN_INSTRUCTION = """\
You are logging into a website using vision and an indexed element list.

The page is ALREADY loaded. Do NOT navigate unless the login form is missing.

Interactive elements are numbered [0], [1], … — use these indices in tools:
  - fill_credential(index, field): fill username or password from the linked
    credential (NEVER use type_text for username/password)
  - type_text(index, text): type plain text (e.g. a 2FA code from get_totp_code)
  - click_element(index): click by index
  - select_option(index, value): select a dropdown option
  - scroll(direction): scroll up or down
  - wait(ms): wait milliseconds
  - get_totp_code(): obtain the current 2FA code (only when a 2FA field appears)
  - done(success, summary): finish when logged in or impossible

Rules:
  - Locate username/email and password fields, fill via fill_credential, submit.
  - If a 2FA/OTP field appears, call get_totp_code() then type_text with the code.
  - If get_totp_code fails, call done(success=false, summary="2fa_required").
  - On success call done(success=true, summary="logged in").
  - One action per turn unless finishing.
"""


def _mask_field(credential_name: str, field: str) -> str:
    return f"<{field} for {credential_name}>"


def _resolve_credential_value(fields: dict[str, str], field: str) -> str:
    if field in fields:
        return fields[field]
    if field == "username":
        for alt in ("email", "user", "login", "username"):
            if alt in fields:
                return fields[alt]
    if field == "password" and "password" in fields:
        return fields["password"]
    raise ValueError(f"credential has no {field!r} field")


class LoginAgent:
    def _has_api_key(self) -> bool:
        return llm_is_configured()

    async def _run_keyless_stub(
        self, on_progress: ProgressCallback
    ) -> dict[str, Any]:
        logger.warning(
            "LoginAgent: no LLM API key configured; emitting demo-mode stub"
        )
        for msg in ("检测登录表单...", "填写凭证...", "提交..."):
            await on_progress(msg)
            await asyncio.sleep(0.3)
        return {
            "completed": False,
            "reason": "no_api_key",
            "summary": "demo-mode stub (configure GOOGLE_API_KEY or OPENAI_API_KEY)",
            "steps": 0,
        }

    async def run_login(
        self,
        *,
        credential_name: str,
        credential_fields: dict[str, str],
        session: Any,
        workflow_id: Optional[str],
        totp_identifier: Optional[str] = None,
        success_criteria: Optional[str] = None,
        on_step: Optional[VisionStepCallback] = None,
        on_progress: Optional[ProgressCallback] = None,
        max_steps: Optional[int] = None,
    ) -> dict[str, Any]:
        if not self._has_api_key():
            stub = await self._run_keyless_stub(
                on_progress or (lambda _: asyncio.sleep(0))
            )
            return stub

        page = await get_page()
        observation: Optional[Observation] = None
        step_index = 0
        action_count = 0
        done_result: Optional[dict[str, Any]] = None
        last_observation: Optional[str] = None
        thought_buffer = ""
        totp_retries = 0
        totp_id = totp_identifier or credential_name

        async def refresh_observation(ref_hint: str) -> Observation:
            nonlocal observation
            observation = await perceive(page, ref_hint=ref_hint)
            return observation

        async def emit_current_step(action: str, target_index: Optional[int]) -> None:
            if observation is None:
                return
            from app.agents.vision import VisionAgent

            agent = VisionAgent()
            await agent._emit_step(
                on_step,
                step_index=step_index,
                thought=thought_buffer or action,
                action=action,
                target_index=target_index,
                screenshot_ref=observation.screenshot_ref,
            )

        async def _invalid_index(index: int) -> dict[str, Any]:
            return {
                "error": f"index {index} not in current observation "
                f"(valid: 0-{max(0, len(observation.elements) - 1) if observation else 0})"
            }

        async def fill_credential(index: int, field: str) -> dict[str, Any]:
            nonlocal action_count, step_index, observation
            if observation is None:
                return {"error": "no observation"}
            if index < 0 or index >= len(observation.elements):
                return await _invalid_index(index)
            try:
                value = _resolve_credential_value(credential_fields, field)
            except ValueError as exc:
                return {"error": str(exc)}
            locator, observation = await resolve_element(page, observation, index)
            if locator is None:
                return {"error": f"element {index} unavailable"}
            await locator.fill(value)
            action_count += 1
            step_index += 1
            await emit_current_step("fill_credential", index)
            return {
                "typed_index": index,
                "field": field,
                "value": _mask_field(credential_name, field),
                "url": page.url,
            }

        async def type_text(index: int, text: str) -> dict[str, Any]:
            nonlocal action_count, step_index, observation
            if observation is None:
                return {"error": "no observation"}
            if index < 0 or index >= len(observation.elements):
                return await _invalid_index(index)
            locator, observation = await resolve_element(page, observation, index)
            if locator is None:
                return {"error": f"element {index} unavailable"}
            await locator.fill(text)
            action_count += 1
            step_index += 1
            await emit_current_step("type_text", index)
            masked = text if len(text) <= 2 else f"<code len={len(text)}>"
            return {"typed_index": index, "text": masked, "url": page.url}

        async def click_element(index: int) -> dict[str, Any]:
            nonlocal action_count, step_index, observation
            if observation is None:
                return {"error": "no observation"}
            if index < 0 or index >= len(observation.elements):
                return await _invalid_index(index)
            locator, observation = await resolve_element(page, observation, index)
            if locator is None:
                return {"error": f"element {index} unavailable"}
            await locator.click()
            action_count += 1
            step_index += 1
            await emit_current_step("click_element", index)
            return {"clicked_index": index, "url": page.url}

        async def select_option(index: int, value: str) -> dict[str, Any]:
            nonlocal action_count, step_index, observation
            if observation is None:
                return {"error": "no observation"}
            if index < 0 or index >= len(observation.elements):
                return await _invalid_index(index)
            locator, observation = await resolve_element(page, observation, index)
            if locator is None:
                return {"error": f"element {index} unavailable"}
            await locator.select_option(value)
            action_count += 1
            step_index += 1
            await emit_current_step("select_option", index)
            return {"selected_index": index, "value": value, "url": page.url}

        async def scroll(direction: Literal["up", "down"]) -> dict[str, Any]:
            nonlocal action_count, step_index
            dy = 500 if direction == "down" else -500
            await page.mouse.wheel(0, dy)
            action_count += 1
            step_index += 1
            await emit_current_step("scroll", None)
            return {"direction": direction, "url": page.url}

        async def wait(ms: int) -> dict[str, Any]:
            nonlocal action_count, step_index
            await asyncio.sleep(max(0, ms) / 1000)
            action_count += 1
            step_index += 1
            await emit_current_step("wait", None)
            return {"waited_ms": ms}

        async def get_totp_code() -> dict[str, Any]:
            nonlocal totp_retries
            if session is None:
                return {"error": "no session for TOTP resolution"}
            try:
                code = resolve_totp_code(
                    totp_id,
                    session,
                    workflow_id=workflow_id,
                    refresh_if_stale=totp_retries == 0,
                )
            except TotpNotAvailable as exc:
                return {"error": str(exc)}
            except Exception as exc:
                return {"error": str(exc)}
            totp_retries += 1
            return {"code": code, "masked": "<totp_code>", "attempt": totp_retries}

        async def done(success: bool, summary: str) -> dict[str, Any]:
            nonlocal done_result
            done_result = {"success": bool(success), "summary": summary}
            await emit_current_step("done", None)
            return done_result

        tools = [
            FunctionTool(fill_credential),
            FunctionTool(type_text),
            FunctionTool(click_element),
            FunctionTool(select_option),
            FunctionTool(scroll),
            FunctionTool(wait),
            FunctionTool(get_totp_code),
            FunctionTool(done),
        ]

        budget = max_steps if max_steps is not None else settings.vision_max_steps
        state = {"stop": False, "tool_calls": 0}

        async def before_tool_callback(tool, args, tool_context):  # type: ignore[no-untyped-def]
            name = getattr(tool, "name", getattr(tool, "__name__", "tool"))
            if on_progress:
                safe_args = dict(args)
                if name == "fill_credential":
                    fld = safe_args.get("field", "field")
                    safe_args["value"] = _mask_field(credential_name, str(fld))
                elif name == "get_totp_code":
                    safe_args = {"masked": "<totp_code>"}
                elif name == "type_text" and "text" in safe_args:
                    t = str(safe_args["text"])
                    safe_args["text"] = t if len(t) <= 2 else f"<code len={len(t)}>"
                try:
                    await on_progress(f"调用 {name}({_truncate(safe_args)})")
                except Exception:
                    pass
            state["tool_calls"] += 1
            if state["tool_calls"] > budget:
                state["stop"] = True
                return {"status": "max_steps_exceeded"}
            return None

        async def after_tool_callback(tool, args, tool_context, tool_response):  # type: ignore[no-untyped-def]
            nonlocal last_observation
            try:
                last_observation = _truncate(tool_response, limit=200)
            except Exception:
                pass
            return None

        agent = LlmAgent(
            name="login",
            model=get_adk_model(),
            instruction=LOGIN_INSTRUCTION,
            tools=tools,
            before_tool_callback=before_tool_callback,
            after_tool_callback=after_tool_callback,
        )
        session_service = InMemorySessionService()
        runner = Runner(
            app_name=_APP_NAME, agent=agent, session_service=session_service
        )

        user_id = "login-user"
        adk_session_id = f"login-{uuid.uuid4().hex[:12]}"
        await session_service.create_session(
            app_name=_APP_NAME, user_id=user_id, session_id=adk_session_id
        )

        observation = await refresh_observation("login-0")
        from app.agents.vision import VisionAgent

        va = VisionAgent()
        await va._emit_step(
            on_step,
            step_index=0,
            thought="observe",
            action="perceive",
            target_index=None,
            screenshot_ref=observation.screenshot_ref,
        )

        criteria_line = ""
        if success_criteria:
            criteria_line = f"\nSuccess criteria: {success_criteria}\n"

        elements_text = format_elements_for_prompt(observation)
        user_text = (
            f"Task: Log in using credential {credential_name!r}.\n"
            f"Current URL: {observation.url}\n"
            f"Page title: {observation.title}\n"
            f"{criteria_line}\n"
            f"Interactive elements:\n{elements_text}\n\n"
            f"Page text summary:\n{observation.page_text_summary}\n"
        )

        parts: list[Any] = [
            types.Part.from_bytes(
                data=observation.screenshot_bytes, mime_type="image/png"
            ),
            types.Part(text=user_text),
        ]
        message = types.Content(role="user", parts=parts)

        async for event in runner.run_async(
            user_id=user_id, session_id=adk_session_id, new_message=message
        ):
            if state["stop"]:
                break
            if done_result is not None:
                break
            if event.content and event.content.parts:
                for p in event.content.parts:
                    if getattr(p, "text", None):
                        thought_buffer = p.text.strip()

        if done_result and done_result.get("success"):
            return {
                "completed": True,
                "summary": done_result.get("summary"),
                "steps": step_index,
            }

        return {
            "completed": False,
            "reason": "login_flow_incomplete",
            "steps": step_index,
            "last_observation": last_observation,
            "agent_summary": (done_result or {}).get("summary"),
        }


__all__ = ["LoginAgent", "LOGIN_INSTRUCTION", "_mask_field", "_resolve_credential_value"]
