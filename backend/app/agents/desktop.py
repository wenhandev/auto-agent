"""Desktop Computer Use agent (observe → act loop over AX + screenshot)."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from app.services.desktop_computer_use.app_lock import hold_desktop_app
from app.services.desktop_computer_use.factory import resolve_desktop_backend
from app.services.desktop_computer_use.protocol import (
    DesktopAppState,
    DesktopComputerUseBackend,
)
from app.services.desktop_computer_use.session import require_interactive_session
from app.services.desktop_perception import compact_desktop_observation
from app.settings import llm_is_configured

logger = logging.getLogger(__name__)

DesktopStepCallback = Callable[[dict[str, Any]], Awaitable[None]]
DesktopDecideFn = Callable[[str, DesktopAppState, str], Awaitable[dict[str, Any]]]


_DESKTOP_DECIDE_PROMPT = """\
You control a native desktop app via accessibility elements.
Return ONLY a JSON object with keys:
  thought (string),
  action (one of: click, type_text, key, scroll, done),
  index (int, required for click/type_text when targeting an element),
  text (string, for type_text),
  key (string, for key),
  direction (up/down/left/right, for scroll),
  amount (int, for scroll),
  done (bool),
  success (bool, when action is done),
  summary (string, when action is done).

Use element indices from the observation. Prefer index over guessing.
When the goal is satisfied, action=done with success=true.
"""


async def llm_desktop_decide(
    app: str,
    state: DesktopAppState,
    instruction: str,
) -> dict[str, Any]:
    """LLM-backed desktop decide; falls back to heuristic on failure."""
    if not llm_is_configured():
        return _heuristic_decide(instruction, state)
    try:
        from app.agents.model import get_genai_client, get_genai_model_id
        from google.genai import types

        client = get_genai_client()
        model_id = get_genai_model_id()
        obs = compact_desktop_observation(state)
        user = (
            f"App: {app}\nGoal/instruction: {instruction}\n"
            f"Observation JSON:\n{json.dumps(obs, ensure_ascii=False)[:12000]}"
        )
        parts: list[Any] = [types.Part.from_text(text=user)]
        if state.screenshot_bytes:
            from app.services.desktop_perception import downsample_png_for_llm

            parts.append(
                types.Part.from_bytes(
                    data=downsample_png_for_llm(state.screenshot_bytes),
                    mime_type="image/png",
                )
            )
        response = await client.aio.models.generate_content(
            model=model_id,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=_DESKTOP_DECIDE_PROMPT,
                temperature=0.2,
            ),
        )
        text = (getattr(response, "text", None) or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        data = json.loads(text)
        if isinstance(data, dict) and data.get("action"):
            return data
    except Exception:
        logger.exception("llm_desktop_decide failed; using heuristic")
    return _heuristic_decide(instruction, state)


def resolve_desktop_decide() -> Optional[DesktopDecideFn]:
    """Return LLM decide when configured; else None (heuristic path)."""
    if llm_is_configured():
        return llm_desktop_decide
    return None


def _heuristic_decide(instruction: str, state: DesktopAppState) -> dict[str, Any]:
    text = (instruction or "").strip()
    lower = text.lower()

    # type / write: "type hello into ..." / "输入 xxx"
    type_m = re.search(
        r"(?:type|write|输入|填写)\s+['\"]?(.+?)['\"]?(?:\s+(?:into|in|到|至)|$)",
        text,
        re.I,
    )
    if type_m or "type " in lower or "输入" in text or "填写" in text:
        payload = type_m.group(1).strip() if type_m else text
        for el in state.elements:
            if el.role in {"textfield", "textarea", "combobox"}:
                return {
                    "thought": f"type into {el.name or el.role}",
                    "action": "type_text",
                    "index": el.index,
                    "text": payload,
                    "done": False,
                }

    for el in state.elements:
        name_l = (el.name or "").lower()
        if any(k in lower for k in ("save", "保存", "click")) and any(
            k in name_l for k in ("save", "保存", "ok", "确定")
        ):
            return {
                "thought": f"click {el.name}",
                "action": "click",
                "index": el.index,
                "done": False,
            }

    for el in state.elements:
        if el.role == "button":
            return {
                "thought": f"click button {el.name}",
                "action": "click",
                "index": el.index,
                "done": False,
            }

    return {
        "thought": "no actionable element",
        "action": "done",
        "success": False,
        "summary": "no actionable desktop element found",
        "done": True,
    }


def _element_name_for_index(
    state: DesktopAppState, index: Any
) -> str:
    try:
        idx = int(index)
    except (TypeError, ValueError):
        return ""
    for el in state.elements:
        if el.index == idx:
            return (el.name or "").strip()
    return ""


def heuristic_goal_satisfied(
    goal: str,
    decision: dict[str, Any],
    state: DesktopAppState,
) -> bool:
    """Return True when a heuristic action plausibly completes the navigate goal.

    Used only when no LLM decide is configured — avoids max_steps dead-ends for
    simple type/click goals without restoring the old "any first success" shortcut.
    """
    action = str(decision.get("action") or "")
    goal_l = (goal or "").strip().lower()
    if not goal_l or action in {"done", "finish"}:
        return False

    if action == "type_text":
        return any(k in goal_l for k in ("type", "write", "输入", "填写"))

    if action == "click":
        el_name = _element_name_for_index(state, decision.get("index")).lower()
        if not el_name:
            return False
        # Goal explicitly targets this control (e.g. "click Save").
        if el_name in goal_l or any(
            tok and tok in goal_l
            for tok in re.split(r"[\s_\-:/\\|]+", el_name)
            if len(tok) >= 2
        ):
            return True
        # Common confirm verbs in both goal and control label.
        confirm = ("save", "保存", "ok", "确定", "submit", "提交", "done", "完成")
        return any(k in goal_l for k in confirm) and any(k in el_name for k in confirm)

    if action == "key":
        key = str(decision.get("key") or "").lower()
        return bool(key) and key in goal_l

    return False


class DesktopAgent:
    def __init__(
        self,
        backend: Optional[DesktopComputerUseBackend] = None,
        *,
        decide: Optional[DesktopDecideFn] = None,
    ) -> None:
        self.backend = backend or resolve_desktop_backend()
        self._decide = decide

    async def _emit(
        self,
        on_step: Optional[DesktopStepCallback],
        **payload: Any,
    ) -> None:
        if on_step is not None:
            await on_step(payload)

    async def _decide_action(
        self,
        app: str,
        instruction: str,
        state: DesktopAppState,
    ) -> dict[str, Any]:
        if self._decide is not None:
            return await self._decide(app, state, instruction)
        return _heuristic_decide(instruction, state)

    async def _apply(
        self,
        app: str,
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        action = str(decision.get("action") or "")
        if action in {"done", "finish"}:
            return {
                "completed": bool(decision.get("success", True)),
                "summary": str(decision.get("summary") or ""),
                "reason": decision.get("reason"),
            }
        if action == "click":
            return await self.backend.click(app, index=int(decision["index"]))
        if action == "type_text":
            return await self.backend.type_text(
                app,
                str(decision.get("text") or ""),
                index=int(decision["index"]) if decision.get("index") is not None else None,
            )
        if action == "key":
            return await self.backend.key(app, str(decision.get("key") or "return"))
        if action == "scroll":
            return await self.backend.scroll(
                app,
                str(decision.get("direction") or "down"),
                int(decision.get("amount") or 3),
            )
        if action == "open_app":
            info = await self.backend.open_app(app)
            return {"ok": True, "app": info.app_id}
        return {"error": f"unknown desktop action {action!r}"}

    async def run_act(
        self,
        app: str,
        instruction: str,
        *,
        on_step: Optional[DesktopStepCallback] = None,
        holder_id: Optional[str] = None,
    ) -> dict[str, Any]:
        require_interactive_session()
        with hold_desktop_app(app, holder_id):
            await self.backend.open_app(app)
            state = await self.backend.get_app_state(app)
            await self._emit(
                on_step,
                app=state.app.app_id,
                step_index=0,
                thought="perceive",
                action="perceive",
                target_index=None,
                screenshot_ref=state.screenshot_ref,
                observation=compact_desktop_observation(state),
            )
            decision = await self._decide_action(app, instruction, state)
            result = await self._apply(app, decision)
            await self._emit(
                on_step,
                app=state.app.app_id,
                step_index=1,
                thought=str(decision.get("thought") or ""),
                action=str(decision.get("action") or ""),
                target_index=decision.get("index"),
                screenshot_ref=state.screenshot_ref,
            )
            if decision.get("done") or decision.get("action") in {"done", "finish"}:
                return {
                    "completed": bool(decision.get("success", True)),
                    "summary": str(decision.get("summary") or instruction),
                    "result": result,
                }
            return {
                "completed": result.get("ok", True) and "error" not in result,
                "summary": str(decision.get("thought") or instruction),
                "result": result,
            }

    async def run_navigate(
        self,
        app: str,
        goal: str,
        *,
        max_steps: int = 10,
        on_step: Optional[DesktopStepCallback] = None,
        holder_id: Optional[str] = None,
        allow_heuristic_short_circuit: bool = False,
    ) -> dict[str, Any]:
        require_interactive_session()
        with hold_desktop_app(app, holder_id):
            await self.backend.open_app(app)
            last_result: dict[str, Any] = {}
            for step in range(max(1, max_steps)):
                state = await self.backend.get_app_state(app)
                await self._emit(
                    on_step,
                    app=state.app.app_id,
                    step_index=step,
                    thought="perceive",
                    action="perceive",
                    target_index=None,
                    screenshot_ref=state.screenshot_ref,
                    observation=compact_desktop_observation(state),
                )
                decision = await self._decide_action(app, goal, state)
                if decision.get("done") or decision.get("action") in {"done", "finish"}:
                    await self._emit(
                        on_step,
                        app=state.app.app_id,
                        step_index=step,
                        thought=str(decision.get("thought") or ""),
                        action="done",
                        target_index=None,
                        screenshot_ref=state.screenshot_ref,
                    )
                    return {
                        "completed": bool(decision.get("success", True)),
                        "summary": str(decision.get("summary") or goal),
                        "steps": step + 1,
                    }
                last_result = await self._apply(app, decision)
                await self._emit(
                    on_step,
                    app=state.app.app_id,
                    step_index=step,
                    thought=str(decision.get("thought") or ""),
                    action=str(decision.get("action") or ""),
                    target_index=decision.get("index"),
                    screenshot_ref=state.screenshot_ref,
                )
                if "error" in last_result:
                    return {
                        "completed": False,
                        "summary": str(last_result.get("error")),
                        "steps": step + 1,
                        "result": last_result,
                    }
                # Explicit test short-circuit only — never in production default.
                if (
                    allow_heuristic_short_circuit
                    and self._decide is None
                    and step == 0
                ):
                    return {
                        "completed": True,
                        "summary": str(decision.get("thought") or goal),
                        "steps": 1,
                        "result": last_result,
                    }
                # Production heuristic path: complete only when the action matches the goal.
                if self._decide is None and heuristic_goal_satisfied(
                    goal, decision, state
                ):
                    return {
                        "completed": True,
                        "summary": str(decision.get("thought") or goal),
                        "steps": step + 1,
                        "result": last_result,
                    }
            return {
                "completed": False,
                "summary": "max_steps exceeded",
                "steps": max_steps,
                "result": last_result,
            }

    async def run_extract(
        self,
        app: str,
        instruction: str,
        *,
        schema: Optional[dict[str, Any]] = None,
        on_step: Optional[DesktopStepCallback] = None,
        holder_id: Optional[str] = None,
    ) -> dict[str, Any]:
        require_interactive_session()
        with hold_desktop_app(app, holder_id):
            await self.backend.open_app(app)
            state = await self.backend.get_app_state(app)
            await self._emit(
                on_step,
                app=state.app.app_id,
                step_index=0,
                thought=instruction,
                action="extract",
                target_index=None,
                screenshot_ref=state.screenshot_ref,
            )
            data = {
                "title": state.title,
                "elements": [
                    {
                        "index": el.index,
                        "role": el.role,
                        "name": el.name,
                        "value": el.value,
                    }
                    for el in state.elements
                ],
            }
            if schema is not None:
                data = {"instruction": instruction, "schema": schema, "raw": data}
            return {"completed": True, "data": data, "summary": instruction}
