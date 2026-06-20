"""LLM-backed decide/reflect hooks for autonomous task mode."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools import FunctionTool
from google.genai import types

from app.agents.autonomous import (
    AgentDecision,
    Memory,
    ToolCall,
    _failed_finish,
    default_decide,
    default_reflect,
)
from app.agents.model import get_adk_model, get_genai_client, get_genai_model_id
from app.schemas_tasks import PlanItem
from app.services import artifact_context
from app.services import cost_tracking as cost_svc
from app.services import llm_traces as trace_svc
from app.services.perception import Observation, format_elements_for_prompt
from app.settings import llm_is_configured


logger = logging.getLogger(__name__)

_APP_NAME = "auto-agent-autonomous"

AUTONOMOUS_INSTRUCTION = """\
You are an autonomous web agent operating one step at a time toward an objective.
Each turn you MUST choose exactly ONE tool call from the offered tools, OR call finish.

Rules:
- The page observation (screenshot + indexed elements) reflects the CURRENT state only.
- Use element indices from the current observation when clicking or typing.
- Call finish(success=true, summary=..., result=...) when the objective is satisfied.
- If the objective requires factual data (prices, text, records), you MUST call extract() and
  finish with a structured `result` or non-empty extracted items — a summary alone is not enough.
- If the objective cannot be met, call finish(success=false, summary=...) explaining why.
- Do not repeat the same failing action; try a different approach or finish.
- When working_memory.last_tool_error is set, read it and follow last_tool_error_hint.
- After a tool error, change strategy: scroll, pick another element, go_back, extract, or finish.
- If working_memory.extracted_items already satisfies the objective, call finish(success=true) instead of retrying a failed click.
- One tool per turn — never plan multiple sequential tools in one response.

Interaction rules:
- For dropdown/select elements (combobox), use select_option(index=<combobox_index>, value=<option_text>) — NOT click_element.
- For text inputs, use type_text(index=..., text=...).
- For buttons and links, use click_element(index=...).

CRITICAL — Data extraction workflow:
1. ORDERS: Navigate to Orders → click ONE order row → immediately call extract() once → navigate to Invoices.
2. INVOICES: Navigate to Invoices → click ONE "Download Summary" button → STOP. When you see a button named "CALL EXTRACT NOW..." in the elements list, call extract() in your VERY NEXT action. Do NOT click that button. Do NOT navigate. Just call extract() immediately.
3. SUPPORT: Navigate to Support → select a category using select_option → type subject → type description → click Next → click Next → click Submit → call extract() once after ticket ID appears.
4. After extracting each section, navigate to the NEXT section immediately.
5. Call finish() when all three sections are in working_memory.extracted_items.

Anti-loop rules:
- If working_memory.extracted_items already has orderId → skip orders, go to Invoices.
- If working_memory.extracted_items already has invoiceId → skip invoices, go to Support.
- If working_memory.extracted_items already has ticketId → skip support, call finish().
- NEVER call extract() more than once for the same data type.
- NEVER navigate back to a section you just left after extraction.
"""


def _record_usage(
    response: Any,
    *,
    system: Optional[str] = None,
    messages: Optional[list[Any]] = None,
    latency_ms: Optional[int] = None,
    vision: bool = False,
) -> None:
    run_id = artifact_context.get_run_id()
    if not run_id:
        return
    usage = cost_svc.usage_from_genai_response(response)
    model_id = get_genai_model_id()
    text = (getattr(response, "text", None) or "").strip()
    trace_svc.record_llm_trace(
        model=model_id,
        system=system,
        messages=messages,
        response=text or None,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        latency_ms=latency_ms,
        vision=vision,
    )
    cost_svc.record_llm_usage(
        run_id,
        model=model_id,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
    )


def _build_prompt(
    *,
    memory: Memory,
    observation: Observation,
    data_schema: Optional[dict[str, Any]],
) -> str:
    ctx = memory.to_context()
    elements_text = format_elements_for_prompt(observation)
    schema_line = ""
    if data_schema:
        schema_line = (
            f"\nRequired finish result schema:\n"
            f"{json.dumps(data_schema, ensure_ascii=False)}\n"
        )
    # Add a context hint if invoice-ready signal is present
    invoice_ready_hint = ""
    for el in observation.elements:
        if "CALL EXTRACT NOW" in (el.name or "") or "extract now" in (el.name or "").lower():
            invoice_ready_hint = (
                "\n⚠️ ACTION REQUIRED: Element [" + str(el.index) + "] '" + el.name + "' is visible. "
                "You MUST call extract() as your NEXT action. Do NOT navigate. Do NOT click anything. Call extract() NOW.\n"
            )
            break

    error_hint = ""
    if memory.last_tool_error:
        error_hint = (
            f"\n⚠️ LAST ACTION FAILED:\n"
            f"Error: {memory.last_tool_error}\n"
            f"Recovery hint: {memory.last_tool_error_hint or 'Try a different approach.'}\n"
            f"Consecutive failures: {memory.consecutive_tool_errors}\n"
        )
        if memory.extracted_items:
            error_hint += (
                "Note: extracted_items may already contain enough data to finish — "
                "consider finish(success=true) instead of repeating the failed action.\n"
            )

    return (
        f"Original objective: {memory.objective}\n"
        "Current page observation is the only source of current page facts; "
        "memory is historical context and may be stale.\n"
        f"Objective: {memory.objective}\n"
        f"Current URL: {observation.url}\n"
        f"Page title: {observation.title}\n"
        f"{schema_line}\n"
        f"{invoice_ready_hint}"
        f"{error_hint}"
        f"Working memory:\n{json.dumps(ctx, ensure_ascii=False, default=str)[:6000]}\n\n"
        f"Interactive elements:\n{elements_text}\n\n"
        f"Page text summary:\n{observation.page_text_summary}\n"
    )


def _build_tools(
    allowed_tools: frozenset[str],
    capture: dict[str, Any],
    state: dict[str, bool],
) -> list[FunctionTool]:
    tools: list[FunctionTool] = []

    def _capture_action(name: str, args: dict[str, Any]) -> None:
        if state["stop"]:
            return
        capture["decision"] = AgentDecision(
            thought=str(capture.get("thought") or ""),
            tool=ToolCall(name=name, args=args),
        )
        state["stop"] = True

    async def finish(
        success: bool,
        summary: str = "",
        result: Any = None,
    ) -> dict[str, Any]:
        if not state["stop"]:
            capture["decision"] = AgentDecision(
                thought=str(capture.get("thought") or ""),
                is_finish=True,
                success=bool(success),
                summary=summary,
                result=result,
            )
            state["stop"] = True
        return {"status": "finish"}

    async def navigate(url: str) -> dict[str, Any]:
        _capture_action("navigate", {"url": url})
        return {"status": "planned"}

    async def click_element(index: int) -> dict[str, Any]:
        _capture_action("click_element", {"index": index})
        return {"status": "planned"}

    async def type_text(index: int, text: str) -> dict[str, Any]:
        _capture_action("type_text", {"index": index, "text": text})
        return {"status": "planned"}

    async def select_option(index: int, value: str) -> dict[str, Any]:
        _capture_action("select_option", {"index": index, "value": value})
        return {"status": "planned"}

    async def scroll(direction: str) -> dict[str, Any]:
        _capture_action("scroll", {"direction": direction})
        return {"status": "planned"}

    async def go_back() -> dict[str, Any]:
        _capture_action("go_back", {})
        return {"status": "planned"}

    async def wait(ms: int = 500) -> dict[str, Any]:
        _capture_action("wait", {"ms": ms})
        return {"status": "planned"}

    async def extract(schema_json: str = "{}") -> dict[str, Any]:
        _capture_action("extract", {"schema_json": schema_json})
        return {"status": "planned"}

    async def http_request(
        method: str,
        url: str,
        headers: Optional[dict[str, Any]] = None,
        body: Any = None,
    ) -> dict[str, Any]:
        _capture_action(
            "http_request",
            {
                "method": method,
                "url": url,
                "headers": headers or {},
                "body": body,
            },
        )
        return {"status": "planned"}

    async def integration(
        app: str,
        resource: str,
        operation: str,
        fields: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        _capture_action(
            "integration",
            {
                "app": app,
                "resource": resource,
                "operation": operation,
                "fields": fields or {},
            },
        )
        return {"status": "planned"}

    builders: dict[str, Any] = {
        "finish": finish,
        "navigate": navigate,
        "click_element": click_element,
        "type_text": type_text,
        "select_option": select_option,
        "scroll": scroll,
        "go_back": go_back,
        "wait": wait,
        "extract": extract,
        "http_request": http_request,
        "integration": integration,
    }

    for name in sorted(allowed_tools):
        if name in builders:
            tools.append(FunctionTool(builders[name]))
        elif name in {
            "set",
            "filter",
            "sort",
            "limit",
            "aggregate",
            "split_out",
            "remove_duplicates",
            "rename_keys",
            "datetime",
        }:

            async def _named_transform(
                params: Optional[dict[str, Any]] = None,
                *,
                _tool_name: str = name,
            ) -> dict[str, Any]:
                _capture_action(_tool_name, {"params": params or {}})
                return {"status": "planned"}

            _named_transform.__name__ = name  # type: ignore[attr-defined]
            tools.append(FunctionTool(_named_transform))

    return tools


def _decide_error_message(exc: Exception) -> str:
    parts: list[str] = []
    cur: BaseException | None = exc
    while cur is not None and len(parts) < 4:
        name = type(cur).__name__
        text = str(cur).strip()
        parts.append(f"{name}: {text}" if text else name)
        cur = cur.__cause__ or cur.__context__
    joined = " | ".join(parts)
    if "401" in joined or "UNAUTHENTICATED" in joined:
        return (
            "Vertex AI authentication failed — run "
            "`gcloud auth application-default login` and retry. "
            f"({joined[:280]})"
        )
    if joined:
        return f"Autonomous agent failed to decide the next action: {joined[:280]}"
    return "Autonomous agent failed to decide the next action"


async def llm_decide(
    *,
    memory: Memory,
    observation: Observation,
    allowed_tools: frozenset[str],
    data_schema: Optional[dict[str, Any]],
) -> AgentDecision:
    if not llm_is_configured():
        return await default_decide(
            memory=memory,
            observation=observation,
            allowed_tools=allowed_tools,
            data_schema=data_schema,
        )

    capture: dict[str, Any] = {"thought": ""}
    state = {"stop": False}
    from app.services.llm_runtime import invalidate_cache

    invalidate_cache()
    tools = _build_tools(allowed_tools, capture, state)

    async def before_tool_callback(tool, args, tool_context):  # type: ignore[no-untyped-def]
        return None

    agent = LlmAgent(
        name="autonomous",
        model=get_adk_model(),
        instruction=AUTONOMOUS_INSTRUCTION,
        tools=tools,
        before_tool_callback=before_tool_callback,
    )
    session_service = InMemorySessionService()
    runner = Runner(app_name=_APP_NAME, agent=agent, session_service=session_service)

    user_id = "autonomous-user"
    session_id = f"autonomous-{uuid.uuid4().hex[:12]}"
    await session_service.create_session(
        app_name=_APP_NAME, user_id=user_id, session_id=session_id
    )

    user_text = _build_prompt(
        memory=memory,
        observation=observation,
        data_schema=data_schema,
    )
    parts: list[Any] = [
        types.Part.from_bytes(data=observation.screenshot_bytes, mime_type="image/png"),
        types.Part(text=user_text),
    ]
    message = types.Content(role="user", parts=parts)

    usage_input: Optional[int] = None
    usage_output: Optional[int] = None
    with trace_svc.LlmCallTracer() as tracer:
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=message,
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
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if getattr(part, "text", None):
                            capture["thought"] = part.text.strip()
        except Exception as exc:
            logger.exception("autonomous llm_decide failed; returning failure")
            from app.services.llm_runtime import invalidate_cache

            invalidate_cache()
            return _failed_finish(_decide_error_message(exc))

    decision = capture.get("decision")
    if isinstance(decision, AgentDecision):
        response_summary = capture.get("thought") or ""
        if decision.tool is not None:
            response_summary = (
                f"{response_summary}\nTool: {decision.tool.name} "
                f"{json.dumps(decision.tool.args, ensure_ascii=False, default=str)}"
            ).strip()
        trace_svc.record_llm_trace(
            model=get_genai_model_id(),
            system=AUTONOMOUS_INSTRUCTION,
            messages=[
                {
                    "role": "user",
                    "content": user_text,
                    "attachments": ["image/png"],
                }
            ],
            response=response_summary or None,
            input_tokens=usage_input,
            output_tokens=usage_output,
            latency_ms=tracer.latency_ms,
            vision=True,
        )
        if decision.tool is not None and not capture.get("thought"):
            decision.thought = decision.tool.name
        return decision

    logger.warning("autonomous llm_decide produced no tool call; returning failure")
    trace_svc.record_llm_trace(
        model=get_genai_model_id(),
        system=AUTONOMOUS_INSTRUCTION,
        messages=[
            {
                "role": "user",
                "content": user_text,
                "attachments": ["image/png"],
            }
        ],
        response=capture.get("thought") or None,
        input_tokens=usage_input,
        output_tokens=usage_output,
        latency_ms=tracer.latency_ms,
        vision=True,
    )
    thought = (capture.get("thought") or "").strip()
    detail = thought if thought else "The model did not invoke any tool"
    return _failed_finish(f"Agent did not select an action: {detail}")


async def llm_reflect(*, memory: Memory) -> list[PlanItem]:
    if not llm_is_configured():
        return await default_reflect(memory=memory)

    prompt = (
        "Update the task plan as JSON only.\n"
        f"Objective: {memory.objective}\n"
        f"Recent steps: {json.dumps(memory.step_summaries[-10:], ensure_ascii=False)}\n"
        f"Extracted items count: {len(memory.extracted_items)}\n"
        f"Current plan: {json.dumps([p.model_dump() for p in memory.plan], ensure_ascii=False)}\n"
        'Return a JSON array of objects: [{"id":"1","text":"...","status":"pending|in_progress|done"}].'
    )
    try:
        client = get_genai_client()
        model_id = get_genai_model_id()
        config = types.GenerateContentConfig(
            system_instruction=(
                "You replan autonomous web tasks. Respond with JSON array only, no markdown."
            )
        )
        system = "You replan autonomous web tasks. Respond with JSON array only, no markdown."
        with trace_svc.LlmCallTracer() as tracer:
            response = await client.aio.models.generate_content(
                model=model_id,
                contents=prompt,
                config=config,
            )
        _record_usage(
            response,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            latency_ms=tracer.latency_ms,
        )
        text = (getattr(response, "text", None) or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        raw = json.loads(text)
        if not isinstance(raw, list):
            raise ValueError("expected JSON array")
        plan = [PlanItem.model_validate(item) for item in raw]
        if plan:
            return plan
    except Exception:
        logger.exception("autonomous llm_reflect failed; using default plan")

    return await default_reflect(memory=memory)


def resolve_autonomous_hooks() -> tuple[Any, Any]:
    """Return (decide_fn, reflect_fn) based on LLM configuration."""
    if llm_is_configured():
        return llm_decide, llm_reflect
    return default_decide, default_reflect


__all__ = ["llm_decide", "llm_reflect", "resolve_autonomous_hooks"]
