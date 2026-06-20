"""Error normalization and user-facing failure messages for autonomous tasks."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from app.settings import llm_is_configured


logger = logging.getLogger(__name__)

REASON_CODES = frozenset({
    "no_progress",
    "time_budget_exhausted",
    "step_budget_exhausted",
    "error",
    "guardrail",
    "schema_validation_failed",
    "aborted",
})

_TECHNICAL_MARKERS = (
    "traceback",
    "playwright",
    "locator.",
    "call log:",
    "timeout 30000ms",
    "file \"",
    "exception:",
    "stack",
    "subtree intercepts",
    "get_by_role",
    "await locator",
    "httpx.",
    "sqlalchemy",
)

_REASON_USER_MESSAGES_EN: dict[str, str] = {
    "no_progress": "The agent stopped making progress on the page and could not continue.",
    "time_budget_exhausted": "The task ran out of time before completing.",
    "step_budget_exhausted": "The task used all allowed steps before completing.",
    "error": "The task stopped due to an unexpected browser error.",
    "guardrail": "The task was blocked by a safety or navigation rule.",
    "schema_validation_failed": "Collected data did not match the required format.",
    "aborted": "The task was cancelled.",
}

_REASON_USER_MESSAGES_ZH: dict[str, str] = {
    "no_progress": "智能体在页面上停滞不前，无法继续完成任务。",
    "time_budget_exhausted": "任务超时，未能完成目标。",
    "step_budget_exhausted": "任务步数用尽，未能完成目标。",
    "error": "浏览器操作出错，任务未能完成。",
    "guardrail": "任务因安全或导航限制被阻止。",
    "schema_validation_failed": "收集到的数据不符合要求的格式。",
    "aborted": "任务已取消。",
}

_CATEGORY_USER_MESSAGES_EN: dict[str, str] = {
    "click_blocked": "Could not click the target because another element is covering it.",
    "timeout": "A browser action timed out before completing.",
    "navigation_blocked": "Navigation was blocked by domain restrictions.",
    "element_missing": "The target element was not found on the page.",
}

_CATEGORY_USER_MESSAGES_ZH: dict[str, str] = {
    "click_blocked": "目标元素被其他内容遮挡，无法点击。",
    "timeout": "页面操作超时，未能完成。",
    "navigation_blocked": "导航被域名限制阻止。",
    "element_missing": "页面上找不到目标元素。",
}

_GENERIC_FAILURE_EN = "The task could not be completed."
_GENERIC_FAILURE_ZH = "任务未能完成。"
_GENERIC_PARTIAL_EN = "The task could not be fully completed, but some information was collected."
_GENERIC_PARTIAL_ZH = "任务未能完全完成，但已收集到部分信息。"


def is_reason_code(reason: Optional[str]) -> bool:
    return bool(reason and reason in REASON_CODES)


def _lang(objective: str) -> str:
    return "zh" if re.search(r"[\u4e00-\u9fff]", objective or "") else "en"


def is_technical_message(text: str) -> bool:
    lowered = (text or "").lower()
    if not lowered.strip():
        return False
    if "error:" in lowered and "autonomous agent failed" in lowered:
        return True
    return any(marker in lowered for marker in _TECHNICAL_MARKERS)


def _strip_call_log(raw: str) -> str:
    text = raw.strip()
    if "Call log:" in text:
        text = text.split("Call log:", 1)[0].strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return text[:400]
    return lines[0][:400]


def normalize_tool_error(raw: str, *, action: str = "") -> dict[str, str]:
    """Turn raw Playwright/tool exceptions into agent-readable error dicts."""
    cleaned = _strip_call_log(raw)
    lowered = cleaned.lower()

    if "timeout" in lowered and (
        "intercept" in lowered or "subtree intercepts" in lowered
    ):
        return {
            "error": "Click failed: the target is covered by another element (overlay or sticky header).",
            "hint": (
                "Do not repeat the same click. Try scroll, a different element, "
                "select_option for dropdowns, or finish(success=true) if extracted_items "
                "already answer the objective."
            ),
            "category": "click_blocked",
        }

    if "timeout" in lowered:
        return {
            "error": f"The {action or 'browser'} action timed out.",
            "hint": "Try wait(), scroll, go_back(), another element, or finish if the objective is already met.",
            "category": "timeout",
        }

    if "not in allowed_domains" in lowered or "blocked (not in" in lowered:
        return {
            "error": cleaned[:300],
            "hint": "Stay within allowed domains or finish with what you have.",
            "category": "navigation_blocked",
        }

    if "unavailable" in lowered or "not found" in lowered:
        return {
            "error": cleaned[:300],
            "hint": "Re-read the current element list and pick a valid index or ref.",
            "category": "element_missing",
        }

    if is_technical_message(cleaned):
        return {
            "error": f"The {action or 'tool'} action failed.",
            "hint": "Try a different approach or finish if the objective is already satisfied.",
            "category": "technical",
        }

    return {
        "error": cleaned[:400],
        "hint": "Try a different approach or finish if the objective is already satisfied.",
        "category": "unknown",
    }


def tool_error_from_exception(exc: Exception, *, action: str = "") -> dict[str, str]:
    return normalize_tool_error(str(exc).strip(), action=action)


def _items_hint(items: list[Any], *, lang: str) -> str:
    if not items:
        return ""
    preview = json.dumps(items[:2], ensure_ascii=False, default=str)
    if len(preview) > 180:
        preview = preview[:177] + "..."
    if lang == "zh":
        return f" 已收集到的信息：{preview}"
    return f" Collected so far: {preview}"


def _message_from_memory(memory_context: Optional[dict[str, Any]], *, lang: str) -> Optional[str]:
    if not memory_context:
        return None

    category = memory_context.get("last_tool_error_category")
    cat_msgs = _CATEGORY_USER_MESSAGES_ZH if lang == "zh" else _CATEGORY_USER_MESSAGES_EN
    if isinstance(category, str) and category in cat_msgs:
        return cat_msgs[category]

    last_error = memory_context.get("last_tool_error")
    if isinstance(last_error, str) and last_error.strip() and not is_technical_message(last_error):
        return last_error.strip()

    recent = memory_context.get("recent_tool_errors") or []
    for err in reversed(recent):
        if isinstance(err, str) and err.strip() and not is_technical_message(err):
            return err.strip()

    steps = memory_context.get("step_summaries") or []
    for step in reversed(steps):
        if isinstance(step, str) and "ERROR:" in step:
            part = step.split("ERROR:", 1)[-1].strip()
            if part and not is_technical_message(part):
                return part[:300]

    return None


def user_failure_message(
    *,
    objective: str,
    summary: str,
    reason: Optional[str] = None,
    items: Optional[list[Any]] = None,
    memory_context: Optional[dict[str, Any]] = None,
) -> str:
    """Best-effort user-facing failure text without code details."""
    items = items or []
    lang = _lang(objective)
    reason_msgs = _REASON_USER_MESSAGES_ZH if lang == "zh" else _REASON_USER_MESSAGES_EN
    generic = _GENERIC_PARTIAL_ZH if items else _GENERIC_FAILURE_ZH
    if lang == "en":
        generic = _GENERIC_PARTIAL_EN if items else _GENERIC_FAILURE_EN

    if summary and not is_technical_message(summary):
        return summary.strip()

    if reason and not is_reason_code(reason) and not is_technical_message(reason):
        return reason.strip()

    memory_msg = _message_from_memory(memory_context, lang=lang)
    if memory_msg:
        return memory_msg + _items_hint(items, lang=lang)

    if reason and is_reason_code(reason):
        base = reason_msgs.get(reason, generic)
        if reason == "no_progress" and items:
            base = (
                _GENERIC_PARTIAL_ZH if lang == "zh" else
                "The agent stopped making progress, but some information was already collected."
            )
        return base + _items_hint(items, lang=lang)

    return generic + _items_hint(items, lang=lang)


async def llm_user_failure_summary(
    *,
    objective: str,
    technical_summary: str,
    reason: Optional[str],
    items: list[Any],
    memory_context: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Ask the LLM for a short, non-technical failure explanation for the user."""
    if not llm_is_configured():
        return None

    from app.agents.model import get_genai_client, get_genai_model_id

    ctx = memory_context or {}
    items_preview = json.dumps(items[:3], ensure_ascii=False, default=str)[:800]
    last_error = (
        ctx.get("last_tool_error")
        or technical_summary
        or ""
    )[:600]
    recent_errors = json.dumps(ctx.get("recent_tool_errors") or [], ensure_ascii=False)[:400]
    lang = _lang(objective)
    lang_rule = (
        "Write in Chinese (简体中文)."
        if lang == "zh"
        else "Write in English."
    )
    prompt = (
        "Write a brief failure explanation for the end user (2-3 sentences, plain language).\n"
        f"{lang_rule}\n"
        "Rules:\n"
        "- Do NOT mention stack traces, Playwright, locators, Python, or internal tool names.\n"
        "- Explain what the agent was trying to do and why it stopped.\n"
        "- If partial data was collected, mention that briefly.\n\n"
        f"Objective: {objective}\n"
        f"Failure reason code: {reason or 'unknown'}\n"
        f"Last browser issue (internal): {last_error}\n"
        f"Recent issues: {recent_errors or 'none'}\n"
        f"Collected items: {items_preview or 'none'}\n"
    )
    try:
        client = get_genai_client()
        response = client.models.generate_content(
            model=get_genai_model_id(),
            contents=prompt,
        )
        text = (getattr(response, "text", None) or "").strip()
        if text and not is_technical_message(text):
            return text[:600]
    except Exception as exc:
        logger.warning("llm_user_failure_summary failed: %s", exc)
    return None


async def resolve_user_failure_message(
    *,
    objective: str,
    summary: str,
    reason: Optional[str] = None,
    items: Optional[list[Any]] = None,
    memory_context: Optional[dict[str, Any]] = None,
) -> str:
    if summary and not is_technical_message(summary):
        return summary.strip()

    if reason and not is_reason_code(reason) and not is_technical_message(reason):
        return reason.strip()

    memory_msg = _message_from_memory(memory_context, lang=_lang(objective))
    if memory_msg and not is_technical_message(memory_msg):
        hint = _items_hint(items or [], lang=_lang(objective))
        return memory_msg + hint

    llm_text = await llm_user_failure_summary(
        objective=objective,
        technical_summary=summary,
        reason=reason,
        items=items or [],
        memory_context=memory_context,
    )
    if llm_text:
        return llm_text

    return user_failure_message(
        objective=objective,
        summary=summary,
        reason=reason,
        items=items,
        memory_context=memory_context,
    )


async def finalize_failure_result(
    result: Any,
    *,
    objective: str,
    memory_context: Optional[dict[str, Any]] = None,
) -> Any:
    """Replace technical summaries with user-facing text on failed TaskResult."""
    from app.schemas_tasks import TaskResult

    if not isinstance(result, TaskResult) or result.success:
        return result

    user_msg = await resolve_user_failure_message(
        objective=objective,
        summary=result.summary,
        reason=result.reason,
        items=list(result.items),
        memory_context=memory_context,
    )
    result.summary = user_msg
    result.user_message = user_msg
    return result


__all__ = [
    "REASON_CODES",
    "finalize_failure_result",
    "is_reason_code",
    "is_technical_message",
    "llm_user_failure_summary",
    "normalize_tool_error",
    "resolve_user_failure_message",
    "tool_error_from_exception",
    "user_failure_message",
]
