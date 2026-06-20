"""Vision-driven browser agent: observe-decide-act loop and extraction."""

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

from app.agents.model import get_adk_model, get_genai_client, get_genai_model_id
from app.services import artifact_context
from app.services import llm_traces as trace_svc
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

_APP_NAME = "auto-agent-vision"

VisionStepCallback = Callable[[dict[str, Any]], Awaitable[None]]
ProgressCallback = Callable[[str], Awaitable[None]]

VISION_INSTRUCTION = """\
You operate a browser using vision and an indexed list of interactive elements.
The page is ALREADY loaded. Do NOT navigate to new URLs unless the goal requires it.

Interactive elements are numbered [0], [1], … — use these indices in tools:
  - click_element(index): click element by index
  - type_text(index, text): type into an input by index
  - select_option(index, value): select an option in a dropdown by index
  - scroll(direction): scroll up or down
  - drag_element(index): drag a slider/handle element horizontally to the right
  - go_back(): browser back
  - wait(ms): wait milliseconds
  - extract(schema_json): return JSON extracted from the page (vision_extract only)
  - done(success, summary): finish — MUST call when the goal is met or impossible

Rules:
  - Be decisive; one action per turn unless finishing.
  - Use element indices from the CURRENT observation only.
  - When the goal is achieved, call done(success=true, summary=...).
  - If stuck, call done(success=false, summary=...) explaining why.
  - If a 2FA/OTP field appears and get_totp_code is available, call it then type_text.
"""


def _vision_instruction(*, totp_enabled: bool) -> str:
    base = VISION_INSTRUCTION
    if not totp_enabled:
        return base
    return base + (
        "\n  - get_totp_code(): obtain the current 2FA code (only when a 2FA field appears)\n"
        "  - If get_totp_code fails, call done(success=false, summary=\"2fa_required\").\n"
    )


def _truncate(value: Any, limit: int = 80) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _validate_json_schema(data: Any, schema: dict[str, Any]) -> tuple[bool, str]:
    """Lightweight JSON Schema validation for common shapes."""
    if schema.get("type") == "object":
        if not isinstance(data, dict):
            return False, "expected object"
        props = schema.get("properties") or {}
        required = schema.get("required") or []
        for key in required:
            if key not in data:
                return False, f"missing required field {key!r}"
        for key, prop_schema in props.items():
            if key in data:
                ok, err = _validate_json_schema(data[key], prop_schema)
                if not ok:
                    return False, f"{key}: {err}"
        return True, ""
    if schema.get("type") == "array":
        if not isinstance(data, list):
            return False, "expected array"
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(data):
                ok, err = _validate_json_schema(item, item_schema)
                if not ok:
                    return False, f"[{i}]: {err}"
        return True, ""
    if schema.get("type") == "string":
        if not isinstance(data, str):
            return False, "expected string"
        return True, ""
    if schema.get("type") == "number":
        if not isinstance(data, (int, float)):
            return False, "expected number"
        return True, ""
    if schema.get("type") == "integer":
        if not isinstance(data, int) or isinstance(data, bool):
            return False, "expected integer"
        return True, ""
    if schema.get("type") == "boolean":
        if not isinstance(data, bool):
            return False, "expected boolean"
        return True, ""
    return True, ""


class VisionAgent:
    def _has_api_key(self) -> bool:
        return llm_is_configured()

    async def _run_keyless_stub(
        self, on_progress: ProgressCallback
    ) -> dict[str, Any]:
        logger.warning(
            "VisionAgent: no LLM API key configured; emitting demo-mode stub"
        )
        for msg in ("分析页面截图...", "决定下一步动作...", "执行点击..."):
            await on_progress(msg)
            await asyncio.sleep(0.7)
        return {
            "completed": False,
            "reason": "no_api_key",
            "summary": "demo-mode stub (configure GOOGLE_API_KEY or OPENAI_API_KEY)",
        }

    async def _emit_step(
        self,
        on_step: Optional[VisionStepCallback],
        *,
        step_index: int,
        thought: str,
        action: str,
        target_index: Optional[int],
        screenshot_ref: str,
    ) -> None:
        if on_step is None:
            return
        await on_step(
            {
                "step_index": step_index,
                "thought": thought,
                "action": action,
                "target_index": target_index,
                "screenshot_ref": screenshot_ref,
            }
        )

    async def _run_loop(
        self,
        *,
        goal: str,
        max_steps: int,
        max_actions: Optional[int] = None,
        mode: Literal["navigate", "act", "extract"] = "navigate",
        schema: Optional[dict[str, Any]] = None,
        on_step: Optional[VisionStepCallback] = None,
        on_progress: Optional[ProgressCallback] = None,
        success_criteria: Optional[str] = None,
        session: Any = None,
        workflow_id: Optional[str] = None,
        totp_identifier: Optional[str] = None,
        captcha_emit: Any = None,
        captcha_run_id: Optional[str] = None,
        captcha_node_id: Optional[str] = None,
        captcha_abort_event: Optional[asyncio.Event] = None,
    ) -> dict[str, Any]:
        page = await get_page()
        observation: Optional[Observation] = None
        step_index = 0
        action_count = 0
        done_result: Optional[dict[str, Any]] = None
        last_observation: Optional[str] = None
        thought_buffer = ""
        totp_retries = 0
        totp_id = totp_identifier

        async def refresh_observation(ref_hint: str) -> Observation:
            nonlocal observation
            observation = await perceive(page, ref_hint=ref_hint)
            if observation.captcha and observation.captcha.present:
                from app.services.captcha.handler import handle_captcha_if_present

                await handle_captcha_if_present(
                    page,
                    observation,
                    emit=captcha_emit,
                    session=session,
                    run_id=captcha_run_id,
                    node_id=captcha_node_id,
                    abort_event=captcha_abort_event,
                )
            return observation

        async def emit_current_step(action: str, target_index: Optional[int]) -> None:
            if observation is None:
                return
            await self._emit_step(
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
            artifact_context.register_sensitive("text", text)
            masked = text if len(text) <= 2 else f"<code len={len(text)}>"
            return {"typed_index": index, "text": masked, "url": page.url}

        async def get_totp_code() -> dict[str, Any]:
            nonlocal totp_retries
            if not totp_id:
                return {"error": "no totp_identifier configured for this run"}
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
            artifact_context.register_sensitive("totp_code", code, credential_type="totp")
            return {"code": code, "masked": "<totp_code>", "attempt": totp_retries}

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

        async def drag_element(index: int) -> dict[str, Any]:
            nonlocal action_count, step_index, observation
            from app.agents.fuzzy import drag_element_horizontal

            if observation is None:
                return {"error": "no observation"}
            if index < 0 or index >= len(observation.elements):
                return await _invalid_index(index)
            locator, observation = await resolve_element(page, observation, index)
            if locator is None:
                return {"error": f"element {index} unavailable"}
            result = await drag_element_horizontal(page, locator)
            action_count += 1
            step_index += 1
            await emit_current_step("drag_element", index)
            result["dragged_index"] = index
            return result

        async def go_back() -> dict[str, Any]:
            nonlocal action_count, step_index
            await page.go_back()
            action_count += 1
            step_index += 1
            await emit_current_step("go_back", None)
            return {"url": page.url}

        async def wait(ms: int) -> dict[str, Any]:
            nonlocal action_count, step_index
            await asyncio.sleep(max(0, ms) / 1000)
            action_count += 1
            step_index += 1
            await emit_current_step("wait", None)
            return {"waited_ms": ms}

        async def extract(schema_json: str = "{}") -> dict[str, Any]:
            nonlocal step_index
            try:
                parsed = json.loads(schema_json) if schema_json.strip() else {}
            except json.JSONDecodeError as exc:
                return {"error": f"invalid schema_json: {exc}"}
            step_index += 1
            await emit_current_step("extract", None)
            return {"status": "extract_requested", "schema": parsed}

        async def done(success: bool, summary: str) -> dict[str, Any]:
            nonlocal done_result
            done_result = {"success": bool(success), "summary": summary}
            await emit_current_step("done", None)
            return done_result

        tools = [
            FunctionTool(click_element),
            FunctionTool(type_text),
            FunctionTool(select_option),
            FunctionTool(scroll),
            FunctionTool(drag_element),
            FunctionTool(go_back),
            FunctionTool(wait),
            FunctionTool(extract),
            FunctionTool(done),
        ]
        if totp_id:
            tools.insert(-2, FunctionTool(get_totp_code))

        if mode == "extract":
            tools = [FunctionTool(extract), FunctionTool(done)]

        state = {"stop": False, "tool_calls": 0}

        async def before_tool_callback(tool, args, tool_context):  # type: ignore[no-untyped-def]
            name = getattr(tool, "name", getattr(tool, "__name__", "tool"))
            if on_progress:
                safe_args = dict(args)
                if name == "get_totp_code":
                    safe_args = {"masked": "<totp_code>"}
                elif name == "type_text" and "text" in safe_args:
                    t = str(safe_args["text"])
                    safe_args["text"] = t if len(t) <= 2 else f"<code len={len(t)}>"
                try:
                    await on_progress(f"调用 {name}({_truncate(safe_args)})")
                except Exception:
                    pass
            state["tool_calls"] += 1
            if max_actions is not None and name not in ("done", "extract"):
                if action_count >= max_actions:
                    state["stop"] = True
                    return {"error": "max_actions_reached"}
            if state["tool_calls"] > max_steps:
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
            name="vision",
            model=get_adk_model(),
            instruction=_vision_instruction(totp_enabled=bool(totp_id)),
            tools=tools,
            before_tool_callback=before_tool_callback,
            after_tool_callback=after_tool_callback,
        )
        session_service = InMemorySessionService()
        runner = Runner(
            app_name=_APP_NAME, agent=agent, session_service=session_service
        )

        user_id = "vision-user"
        session_id = f"vision-{uuid.uuid4().hex[:12]}"
        await session_service.create_session(
            app_name=_APP_NAME, user_id=user_id, session_id=session_id
        )

        observation = await refresh_observation("step-0")
        await self._emit_step(
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
            f"Goal: {goal}\n"
            f"Current URL: {observation.url}\n"
            f"Page title: {observation.title}\n"
            f"{criteria_line}\n"
            f"Interactive elements:\n{elements_text}\n\n"
            f"Page text summary:\n{observation.page_text_summary}\n"
        )

        if mode == "extract":
            schema_hint = json.dumps(schema or {}, ensure_ascii=False)
            user_text += (
                f"\nExtraction instruction: {goal}\n"
                f"Target JSON schema: {schema_hint}\n"
                "Call extract() then done(success=true, summary=<json string of extracted data>)."
            )

        parts: list[Any] = [
            types.Part.from_bytes(data=observation.screenshot_bytes, mime_type="image/png"),
            types.Part(text=user_text),
        ]
        message = types.Content(role="user", parts=parts)

        usage_input: Optional[int] = None
        usage_output: Optional[int] = None
        system_instruction = _vision_instruction(totp_enabled=bool(totp_id))
        with trace_svc.LlmCallTracer() as tracer:
            async for event in runner.run_async(
                user_id=user_id, session_id=session_id, new_message=message
            ):
                meta = getattr(event, "usage_metadata", None)
                if meta is not None:
                    pt = getattr(meta, "prompt_token_count", None)
                    ct = getattr(meta, "candidates_token_count", None)
                    if isinstance(pt, int):
                        usage_input = pt
                    if isinstance(ct, int):
                        usage_output = ct
                if state["stop"]:
                    break
                if done_result is not None:
                    break
                if max_actions is not None and action_count >= max_actions and mode == "act":
                    break
                if event.content and event.content.parts:
                    for p in event.content.parts:
                        if getattr(p, "text", None):
                            thought_buffer = p.text.strip()

        trace_svc.record_llm_trace(
            model=get_genai_model_id(),
            system=system_instruction,
            messages=[
                {
                    "role": "user",
                    "content": user_text,
                    "attachments": ["image/png"],
                }
            ],
            response=thought_buffer or None,
            input_tokens=usage_input,
            output_tokens=usage_output,
            latency_ms=tracer.latency_ms,
            vision=True,
        )

        if mode == "extract":
            return await self._finalize_extract(
                done_result=done_result,
                schema=schema,
                goal=goal,
                last_observation=last_observation,
                steps=step_index,
            )

        if done_result and done_result.get("success"):
            return {
                "completed": True,
                "summary": done_result.get("summary"),
                "steps": step_index,
            }

        return {
            "completed": False,
            "reason": "max_steps_reached",
            "steps": step_index,
            "last_observation": last_observation,
        }

    async def _finalize_extract(
        self,
        *,
        done_result: Optional[dict[str, Any]],
        schema: Optional[dict[str, Any]],
        goal: str,
        last_observation: Optional[str],
        steps: int,
    ) -> dict[str, Any]:
        if not done_result:
            return {
                "completed": False,
                "reason": "max_steps_reached",
                "steps": steps,
                "last_observation": last_observation,
            }

        summary = str(done_result.get("summary") or "")
        if not done_result.get("success"):
            return {
                "completed": False,
                "reason": "extract_failed",
                "summary": summary,
                "steps": steps,
            }

        if not schema:
            try:
                data = json.loads(summary)
            except json.JSONDecodeError:
                data = {"text": summary}
            return {"completed": True, "data": data, "steps": steps}

        try:
            data = json.loads(summary)
        except json.JSONDecodeError:
            repaired = await self._repair_extract(summary, schema, goal)
            if repaired is None:
                return {
                    "completed": False,
                    "reason": "schema_validation_failed",
                    "raw": summary,
                    "steps": steps,
                }
            data = repaired

        ok, err = _validate_json_schema(data, schema)
        if not ok:
            repaired = await self._repair_extract(summary, schema, goal, error=err)
            if repaired is None:
                return {
                    "completed": False,
                    "reason": "schema_validation_failed",
                    "error": err,
                    "raw": summary,
                    "steps": steps,
                }
            data = repaired
            ok, err = _validate_json_schema(data, schema)
            if not ok:
                return {
                    "completed": False,
                    "reason": "schema_validation_failed",
                    "error": err,
                    "steps": steps,
                }

        return {"completed": True, "data": data, "steps": steps}

    async def _repair_extract(
        self,
        raw: str,
        schema: dict[str, Any],
        goal: str,
        error: str = "invalid JSON",
    ) -> Optional[Any]:
        """Single repair attempt using a direct genai call (mockable in tests)."""
        from app.agents.model import get_genai_client, get_genai_model_id

        prompt = (
            f"The following extraction did not match the schema.\n"
            f"Instruction: {goal}\n"
            f"Schema: {json.dumps(schema, ensure_ascii=False)}\n"
            f"Validation error: {error}\n"
            f"Raw output: {raw}\n"
            "Return ONLY valid JSON matching the schema."
        )
        try:
            client = get_genai_client()
            model_id = get_genai_model_id()
            system = "You repair JSON to match a JSON Schema."
            config = types.GenerateContentConfig(system_instruction=system)
            with trace_svc.LlmCallTracer() as tracer:
                response = await client.aio.models.generate_content(
                    model=model_id, contents=prompt, config=config
                )
            text = getattr(response, "text", None) or ""
            usage = None
            try:
                from app.services import cost_tracking as cost_svc

                usage = cost_svc.usage_from_genai_response(response)
            except Exception:
                usage = {"input_tokens": None, "output_tokens": None}
            trace_svc.record_llm_trace(
                model=model_id,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                response=text.strip() or None,
                input_tokens=usage.get("input_tokens") if usage else None,
                output_tokens=usage.get("output_tokens") if usage else None,
                latency_ms=tracer.latency_ms,
            )
            return json.loads(text.strip())
        except Exception as exc:
            logger.warning("vision extract repair failed: %s", exc)
            return None

    async def run_navigate(
        self,
        goal: str,
        *,
        max_steps: Optional[int] = None,
        success_criteria: Optional[str] = None,
        on_step: Optional[VisionStepCallback] = None,
        on_progress: Optional[ProgressCallback] = None,
        session: Any = None,
        workflow_id: Optional[str] = None,
        totp_identifier: Optional[str] = None,
        captcha_emit: Any = None,
        captcha_run_id: Optional[str] = None,
        captcha_node_id: Optional[str] = None,
        captcha_abort_event: Optional[asyncio.Event] = None,
    ) -> dict[str, Any]:
        if not self._has_api_key():
            if on_progress:
                return await self._run_keyless_stub(on_progress)
            return await self._run_keyless_stub(lambda _: asyncio.sleep(0))
        budget = max_steps if max_steps is not None else settings.vision_max_steps
        return await self._run_loop(
            goal=goal,
            max_steps=max(1, budget),
            mode="navigate",
            on_step=on_step,
            on_progress=on_progress,
            success_criteria=success_criteria,
            session=session,
            workflow_id=workflow_id,
            totp_identifier=totp_identifier,
            captcha_emit=captcha_emit,
            captcha_run_id=captcha_run_id,
            captcha_node_id=captcha_node_id,
            captcha_abort_event=captcha_abort_event,
        )

    async def run_act(
        self,
        instruction: str,
        *,
        on_step: Optional[VisionStepCallback] = None,
        on_progress: Optional[ProgressCallback] = None,
        session: Any = None,
        workflow_id: Optional[str] = None,
        totp_identifier: Optional[str] = None,
        captcha_emit: Any = None,
        captcha_run_id: Optional[str] = None,
        captcha_node_id: Optional[str] = None,
        captcha_abort_event: Optional[asyncio.Event] = None,
    ) -> dict[str, Any]:
        if not self._has_api_key():
            if on_progress:
                return await self._run_keyless_stub(on_progress)
            return await self._run_keyless_stub(lambda _: asyncio.sleep(0))
        return await self._run_loop(
            goal=instruction,
            max_steps=settings.vision_max_steps,
            max_actions=1,
            mode="act",
            on_step=on_step,
            on_progress=on_progress,
            session=session,
            workflow_id=workflow_id,
            totp_identifier=totp_identifier,
            captcha_emit=captcha_emit,
            captcha_run_id=captcha_run_id,
            captcha_node_id=captcha_node_id,
            captcha_abort_event=captcha_abort_event,
        )

    async def run_extract(
        self,
        instruction: str,
        *,
        schema: Optional[dict[str, Any]] = None,
        on_step: Optional[VisionStepCallback] = None,
        on_progress: Optional[ProgressCallback] = None,
        session: Any = None,
        workflow_id: Optional[str] = None,
        totp_identifier: Optional[str] = None,
        captcha_emit: Any = None,
        captcha_run_id: Optional[str] = None,
        captcha_node_id: Optional[str] = None,
        captcha_abort_event: Optional[asyncio.Event] = None,
    ) -> dict[str, Any]:
        if not self._has_api_key():
            if on_progress:
                return await self._run_keyless_stub(on_progress)
            return await self._run_keyless_stub(lambda _: asyncio.sleep(0))
        return await self._run_loop(
            goal=instruction,
            max_steps=settings.vision_max_steps,
            mode="extract",
            schema=schema,
            on_step=on_step,
            on_progress=on_progress,
            session=session,
            workflow_id=workflow_id,
            totp_identifier=totp_identifier,
            captcha_emit=captcha_emit,
            captcha_run_id=captcha_run_id,
            captcha_node_id=captcha_node_id,
            captcha_abort_event=captcha_abort_event,
        )


__all__ = ["VisionAgent", "VISION_INSTRUCTION", "_validate_json_schema"]
