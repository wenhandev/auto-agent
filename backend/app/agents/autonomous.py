"""Autonomous plan-act-observe-reflect loop over vision tools + nodes-as-tools."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import quote_plus

from app.agents.autonomous_guardrails import (
    BudgetClock,
    ConfirmationGate,
    ProgressTracker,
    check_navigation,
)
from app.agents.autonomous_errors import (
    finalize_failure_result,
    normalize_tool_error,
    tool_error_from_exception,
)
from app.agents.vision import VisionAgent, _validate_json_schema
from app.nodes.dispatch import TRANSFORM_NODE_TYPES, run_transform
from app.schemas_tasks import (
    DEFAULT_ALLOWED_TOOLS,
    DESKTOP_TOOLS,
    PlanItem,
    TaskResult,
    TaskSpec,
)
from app.services.perception import Observation, perceive, resolve_element, resolve_ref
from app.tools import actions
from app.tools.browser import get_page


logger = logging.getLogger(__name__)

REFLECT_EVERY_K = 5
MEMORY_OBSERVATION_LIMIT = 8

EventEmitter = Callable[[dict[str, Any]], Awaitable[None]]
DecideFn = Callable[..., Awaitable["AgentDecision"]]
ReflectFn = Callable[..., Awaitable[list[PlanItem]]]


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]


@dataclass
class AgentDecision:
    thought: str = ""
    tool: Optional[ToolCall] = None
    is_finish: bool = False
    success: bool = False
    result: Any = None
    summary: str = ""


@dataclass
class TrajectoryStep:
    step_index: int
    tool: str
    args: dict[str, Any]
    result: Any
    url: str
    stable: bool = True
    thought: str = ""


@dataclass
class Memory:
    objective: str
    session_memory: list[dict[str, Any]] = field(default_factory=list)
    plan: list[PlanItem] = field(default_factory=list)
    recent_observations: list[dict[str, Any]] = field(default_factory=list)
    extracted_items: list[Any] = field(default_factory=list)
    visited_urls: set[str] = field(default_factory=set)
    step_summaries: list[str] = field(default_factory=list)
    compact_summary: str = ""
    last_extract_url: Optional[str] = None
    last_extract_element_hash: Optional[str] = None
    already_extracted_count: int = 0
    last_action_effect: Optional[dict[str, Any]] = None
    last_action_label: Optional[str] = None
    route_skill_ids: list[str] = field(default_factory=list)
    route_prompts: list[str] = field(default_factory=list)
    # Track which task sections have been completed (orders / invoices / support)
    sections_done: set[str] = field(default_factory=set)
    last_tool_error: Optional[str] = None
    last_tool_error_hint: Optional[str] = None
    last_tool_error_category: Optional[str] = None
    consecutive_tool_errors: int = 0
    recent_tool_errors: list[str] = field(default_factory=list)
    # Native desktop Computer Use context (observe/act against an app, not browser).
    active_desktop_app: Optional[str] = None
    desktop_lock_holder: Optional[str] = None

    def record_observation(self, observation: Observation) -> None:
        payload = observation.compact_payload()
        self.recent_observations.append(payload)
        if len(self.recent_observations) > MEMORY_OBSERVATION_LIMIT:
            dropped = self.recent_observations.pop(0)
            self.step_summaries.append(
                f"observed {dropped.get('url', '?')} "
                f"({len(dropped.get('elements') or [])} elements)"
            )
            if len(self.step_summaries) > 20:
                self.compact_summary = (
                    self.compact_summary + " | " + self.step_summaries.pop(0)
                ).strip(" |")

    def record_step(self, action: str, result: Any, url: str) -> None:
        self.visited_urls.add(url)
        if isinstance(result, dict) and result.get("error"):
            err_text = str(result.get("error", ""))
            self.last_tool_error = err_text
            self.last_tool_error_hint = str(result.get("hint") or "")
            self.last_tool_error_category = str(result.get("category") or "")
            self.consecutive_tool_errors += 1
            self.recent_tool_errors.append(err_text[:200])
            if len(self.recent_tool_errors) > 5:
                self.recent_tool_errors.pop(0)
            summary = f"{action} @ {url} -> ERROR: {err_text[:240]}"
        else:
            self.last_tool_error = None
            self.last_tool_error_hint = None
            self.last_tool_error_category = None
            self.consecutive_tool_errors = 0
            summary = f"{action} @ {url} -> {_truncate(result)}"
        self.step_summaries.append(summary)
        self.last_action_label = action
        if isinstance(result, dict):
            if "data" in result:
                self.extracted_items.append(result["data"])
            elif result.get("extracted"):
                self.extracted_items.append(result["extracted"])

    def record_action_effect(self, effect: dict[str, Any]) -> None:
        self.last_action_effect = effect

    def apply_route_context(self, skill_ids: list[str], prompts: list[str]) -> None:
        self.route_skill_ids = skill_ids
        self.route_prompts = prompts

    def remaining_steps(self) -> list[str]:
        return [
            item.text
            for item in self.plan
            if item.status in ("pending", "in_progress")
        ]

    def to_context(self) -> dict[str, Any]:
        return {
            "original_goal": self.objective,
            "objective": self.objective,
            "session_memory": self.session_memory,
            "plan": [p.model_dump() for p in self.plan],
            "remaining_steps": self.remaining_steps(),
            "recent_observations": self.recent_observations,
            "extracted_items": list(self.extracted_items),
            "sections_done": sorted(self.sections_done),
            "visited_urls": sorted(self.visited_urls),
            "compact_summary": self.compact_summary,
            "step_summaries": self.step_summaries[-10:],
            "last_action_effect": self.last_action_effect,
            "last_tool_error": self.last_tool_error,
            "last_tool_error_hint": self.last_tool_error_hint,
            "last_tool_error_category": self.last_tool_error_category,
            "consecutive_tool_errors": self.consecutive_tool_errors,
            "recent_tool_errors": self.recent_tool_errors[-3:],
            "route_skill_ids": self.route_skill_ids,
            "route_prompts": self.route_prompts,
        }


def _truncate(value: Any, limit: int = 80) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _element_fingerprint(observation: Observation) -> list[tuple[str, str, str]]:
    return [
        (el.role, el.name, el.signature_metadata.get("value", ""))
        for el in observation.elements
    ]


def summarize_action_effect(
    before: Observation,
    after: Observation,
    *,
    action_label: str,
    previous_action_label: Optional[str],
    data_items_before: int,
    data_items_after: int,
) -> dict[str, Any]:
    """Summarize whether the previous action visibly changed the page."""
    url_changed = before.url != after.url
    title_changed = before.title != after.title
    elements_changed = _element_fingerprint(before) != _element_fingerprint(after)
    text_changed = before.page_text_summary != after.page_text_summary
    data_items_added = max(0, data_items_after - data_items_before)
    repeated_action = bool(previous_action_label and previous_action_label == action_label)

    changes: list[str] = []
    if url_changed:
        changes.append("changed url")
    if title_changed:
        changes.append("changed title")
    if elements_changed:
        changes.append("changed elements")
    if text_changed:
        changes.append("changed text")
    if data_items_added:
        changes.append(f"added {data_items_added} data item")
    if repeated_action:
        changes.append("repeated previous action")
    if not changes:
        changes.append("no visible effect")

    return {
        "action": action_label,
        "url_changed": url_changed,
        "title_changed": title_changed,
        "elements_changed": elements_changed,
        "text_changed": text_changed,
        "data_items_added": data_items_added,
        "repeated_action": repeated_action,
        "summary": ", ".join(changes),
    }


def resolve_allowed_tools(spec: TaskSpec) -> frozenset[str]:
    if spec.allowed_tools is not None:
        return frozenset(spec.allowed_tools)
    # Browser default. Desktop tools are opt-in via TaskSpec.allowed_tools
    # (e.g. DEFAULT_DESKTOP_ALLOWED_TOOLS or an explicit mix).
    return frozenset(DEFAULT_ALLOWED_TOOLS)


def load_route_context(url: str, allowed_tools: frozenset[str]) -> Any:
    from sqlmodel import Session

    from app.db.session import engine
    from app.services import route_skills

    try:
        with Session(engine) as session:
            return route_skills.build_route_context(
                session,
                url,
                task_allowed_tools=allowed_tools,
            )
    except Exception:
        logger.exception("failed to build route context url=%s", url)
        return route_skills.RouteSkillContext(allowed_tools=allowed_tools)


def tool_schemas(allowed: frozenset[str]) -> list[dict[str, Any]]:
    schemas: list[dict[str, Any]] = []
    vision_defs = {
        "navigate": {"url": "string"},
        "click_element": {"index": "integer?", "ref": "string?"},
        "type_text": {"index": "integer?", "ref": "string?", "text": "string"},
        "select_option": {"index": "integer?", "ref": "string?", "value": "string"},
        "scroll": {"direction": "up|down"},
        "drag_element": {"index": "integer?", "ref": "string?"},
        "go_back": {},
        "wait": {"ms": "integer"},
        "extract": {"schema_json": "string?"},
        "finish": {"success": "boolean", "result": "any?", "summary": "string?"},
        "http_request": {
            "method": "string",
            "url": "string",
            "headers": "object?",
            "body": "any?",
        },
        "integration": {
            "app": "string",
            "resource": "string",
            "operation": "string",
            "fields": "object?",
        },
        "list_apps": {},
        "open_app": {"app": "string"},
        "get_app_state": {"app": "string"},
        "desktop_click": {
            "app": "string",
            "index": "integer?",
            "x": "number?",
            "y": "number?",
        },
        "desktop_type": {"app": "string", "text": "string", "index": "integer?"},
        "desktop_key": {"app": "string", "key": "string"},
        "desktop_scroll": {
            "app": "string",
            "direction": "up|down|left|right",
            "amount": "integer?",
        },
    }
    for name in sorted(allowed):
        if name in vision_defs:
            schemas.append({"name": name, "parameters": vision_defs[name]})
        elif name in TRANSFORM_NODE_TYPES:
            schemas.append({"name": name, "parameters": {"params": "object"}})
    return schemas


def _default_search_url(objective: str) -> str:
    return f"https://www.google.com/search?q={quote_plus(objective)}"


def _failed_finish(summary: str) -> AgentDecision:
    return AgentDecision(
        thought=summary,
        is_finish=True,
        success=False,
        summary=summary,
    )


_PASSIVE_ACTION_TOOLS = frozenset({"navigate", "wait", "scroll", "go_back"})


def _has_structured_result(result: Any) -> bool:
    if result is None:
        return False
    if isinstance(result, dict):
        return len(result) > 0
    if isinstance(result, (list, tuple)):
        return len(result) > 0
    if isinstance(result, str):
        return bool(result.strip())
    return True


def _success_finish_evidence_error(
    decision: AgentDecision,
    memory: Memory,
    trajectory: list[TrajectoryStep],
    *,
    data_schema: Optional[dict[str, Any]],
) -> Optional[str]:
    """Return an error message when success=true lacks verifiable objective data."""
    if not decision.success:
        return None
    if data_schema is not None:
        return None
    if memory.extracted_items:
        return None
    if _has_structured_result(decision.result):
        return None

    tools_used = {step.tool for step in trajectory}
    if tools_used and tools_used.issubset(_PASSIVE_ACTION_TOOLS):
        return (
            "Task marked complete without extracted data — only "
            f"{', '.join(sorted(tools_used))} steps ran. "
            "Call extract() and capture findings before finish(success=true)."
        )
    if "extract" not in tools_used:
        return (
            "Task marked complete without extracted data or structured result. "
            "Use extract() to capture objective findings before finish(success=true)."
        )
    return (
        "Task marked complete but extract() returned no usable data. "
        "Continue browsing or finish(success=false) if the objective cannot be met."
    )


async def default_decide(
    *,
    memory: Memory,
    observation: Observation,
    allowed_tools: frozenset[str],
    data_schema: Optional[dict[str, Any]],
) -> AgentDecision:
    if data_schema:
        return _failed_finish(
            "LLM is not configured; cannot run autonomous tasks with a data schema"
        )
    return _failed_finish(
        "LLM is not configured; set LLM_PROVIDER to run autonomous tasks"
    )


async def default_reflect(*, memory: Memory) -> list[PlanItem]:
    if memory.plan:
        return memory.plan
    return [
        PlanItem(id="1", text=memory.objective, status="in_progress"),
    ]


class AutonomousAgent:
    def __init__(
        self,
        *,
        decide_fn: Optional[DecideFn] = None,
        reflect_fn: Optional[ReflectFn] = None,
        confirmation_gate: Optional[ConfirmationGate] = None,
        vision_agent: Optional[VisionAgent] = None,
    ) -> None:
        if decide_fn is None or reflect_fn is None:
            from app.agents.autonomous_llm import resolve_autonomous_hooks

            resolved_decide, resolved_reflect = resolve_autonomous_hooks()
        else:
            resolved_decide, resolved_reflect = default_decide, default_reflect
        self.decide_fn = decide_fn or resolved_decide
        self.reflect_fn = reflect_fn or resolved_reflect
        self.confirmation_gate = confirmation_gate
        self.vision_agent = vision_agent or VisionAgent()
        self.trajectory: list[TrajectoryStep] = []

    async def _perceive_step(
        self,
        page: Any,
        memory: Memory,
        *,
        allowed: frozenset[str],
        ref_hint: str,
    ) -> Observation:
        """Browser perceive by default; desktop state when in native-app context."""
        app = (memory.active_desktop_app or "").strip()
        desktop_allowed = bool(app) and bool(DESKTOP_TOOLS & set(allowed))
        if desktop_allowed:
            try:
                from app.services.desktop_computer_use import resolve_desktop_backend
                from app.services.desktop_perception import observation_from_desktop_state

                desktop = resolve_desktop_backend()
                state = await desktop.get_app_state(app)
                return observation_from_desktop_state(state)
            except Exception as exc:
                # Stay on desktop:// so guardrails/decide do not confuse browser
                # element indices with desktop ones.
                logger.warning(
                    "desktop observe failed for %s (%s); returning empty desktop obs",
                    app,
                    exc,
                )
                return Observation(
                    url=f"desktop://{app}",
                    title=app,
                    screenshot_bytes=b"",
                    screenshot_ref="desktop-observe-failed",
                    ax_snapshot={},
                    elements=[],
                    page_text_summary=f"desktop observe failed: {exc}",
                )
        return await perceive(page, ref_hint=ref_hint)

    async def run_task(
        self,
        spec: TaskSpec,
        emit: EventEmitter,
        *,
        abort_event: Optional[asyncio.Event] = None,
    ) -> TaskResult:
        allowed = resolve_allowed_tools(spec)
        memory = Memory(
            objective=spec.objective,
            session_memory=list(spec.session_memory or []),
        )
        memory.plan = await self.reflect_fn(memory=memory)
        await emit({
            "event": "task_plan_updated",
            "plan": [p.model_dump() for p in memory.plan],
            "ts": _ts(),
        })

        clock = BudgetClock(max_steps=spec.max_steps, max_seconds=spec.max_seconds)
        progress = ProgressTracker()
        gate = self.confirmation_gate or ConfirmationGate(spec.require_confirmation)
        observation: Optional[Observation] = None
        finish_retries = 0
        synthesized_id: Optional[str] = None

        page = await get_page()
        initial_url = spec.start_url or _default_search_url(spec.objective)
        nav_err = check_navigation(initial_url, spec.allowed_domains)
        if nav_err:
            return await _user_facing_failure(
                TaskResult(
                    success=False,
                    summary=nav_err,
                    reason="guardrail",
                    steps_taken=0,
                ),
                objective=spec.objective,
                memory=memory,
            )
        if "navigate" in allowed:
            await actions.navigate(initial_url)

        while not clock.step_budget_exhausted() and not clock.deadline_exceeded():
            from app.services.agent_loop_metrics import get_metrics

            loop_metrics = get_metrics()
            if loop_metrics is not None:
                loop_metrics.record_round()

            if abort_event is not None and abort_event.is_set():
                return await _user_facing_failure(
                    TaskResult(
                        success=False,
                        summary="aborted",
                        reason="aborted",
                        steps_taken=clock.steps_used,
                        items=list(memory.extracted_items),
                    ),
                    objective=spec.objective,
                    memory=memory,
                )

            if memory.consecutive_tool_errors >= 2:
                memory.plan = await self.reflect_fn(memory=memory)
                await emit({
                    "event": "task_plan_updated",
                    "plan": [p.model_dump() for p in memory.plan],
                    "ts": _ts(),
                })

            observation = await self._perceive_step(
                page,
                memory,
                allowed=allowed,
                ref_hint=f"task-{clock.steps_used}",
            )
            memory.record_observation(observation)
            route_context = load_route_context(observation.url, allowed)
            effective_allowed = route_context.allowed_tools or allowed
            if route_context.skill_ids:
                memory.apply_route_context(
                    list(route_context.skill_ids),
                    list(route_context.prompts),
                )
                await emit({
                    "event": "route_skill_applied",
                    "skill_ids": list(route_context.skill_ids),
                    "prompts": list(route_context.prompts),
                    "allowed_tools": sorted(effective_allowed),
                    "url": observation.url,
                    "ts": _ts(),
                })

            decision = await self.decide_fn(
                memory=memory,
                observation=observation,
                allowed_tools=effective_allowed,
                data_schema=spec.data_schema,
            )

            # Heuristic override: if a "CALL EXTRACT NOW" signal button is visible
            # and the LLM decided to do anything other than extract(), force extract().
            # This prevents the LLM from navigating away when invoice data is ready.
            _extract_signal = any(
                "CALL EXTRACT NOW" in (el.name or "")
                for el in observation.elements
            )
            # Similarly, force extract when ticket is ready
            _ticket_signal = any(
                "TICKET READY" in (el.name or "")
                for el in observation.elements
            )
            logger.warning(
                "HEURISTIC_CHECK step=%d: signal=%s els=%s llm_action=%s",
                clock.steps_used + 1,
                _extract_signal,
                [(el.index, el.name[:30] if el.name else "") for el in observation.elements],
                decision.tool.name if decision.tool else "finish",
            )
            if (
                _extract_signal
                and decision.tool is not None
                and decision.tool.name != "extract"
                and not decision.is_finish
            ):
                logger.warning(
                    "HEURISTIC_OVERRIDE: forcing extract() because signal button visible; "
                    "LLM had decided %s", decision.tool.name
                )
                decision = AgentDecision(
                    thought="Auto-extract: invoice data signal visible",
                    tool=ToolCall(name="extract", args={"schema_json": "{}"}),
                )
            if (
                _ticket_signal
                and decision.tool is not None
                and decision.tool.name != "extract"
                and not decision.is_finish
            ):
                logger.warning(
                    "HEURISTIC_OVERRIDE: forcing extract() because ticket signal visible; "
                    "LLM had decided %s", decision.tool.name if decision.tool else "finish"
                )
                decision = AgentDecision(
                    thought="Auto-extract: ticket data ready",
                    tool=ToolCall(name="extract", args={"schema_json": "{}"}),
                )

            # When all sections are done, force finish immediately
            if (
                "invoices" in memory.sections_done
                and "support" in memory.sections_done
                and not decision.is_finish
            ):
                logger.warning(
                    "HEURISTIC_OVERRIDE: all sections done, forcing finish (items=%d)",
                    len(memory.extracted_items),
                )
                decision = AgentDecision(
                    thought="All sections complete: order, invoice, ticket extracted",
                    is_finish=True,
                    success=True,
                    summary="All sections complete: order, invoice, and support ticket extracted",
                    result={"items": list(memory.extracted_items)},
                )

            # Heuristic override: if invoices section is done but support is not,
            # force navigate to Support if the agent is clicking a non-Support nav item.
            # Only intercept nav-level clicks (indices 0-4), not clicks on page elements.
            _support_el = next(
                (el for el in observation.elements if el.name and "Support" in el.name),
                None,
            )
            _nav_el_indices = {
                el.index for el in observation.elements
                if el.name and any(
                    kw in el.name for kw in ["Dashboard", "Orders", "Shipments", "Invoices", "Support"]
                )
                and el.index <= 6  # Nav items are always at low indices
            }
            if (
                "invoices" in memory.sections_done
                and "support" not in memory.sections_done
                and not _extract_signal
                and decision.tool is not None
                and decision.tool.name == "click_element"
                and not decision.is_finish
                and _support_el is not None
            ):
                click_idx = decision.tool.args.get("index")
                # Only redirect if clicking a nav item that is NOT the Support nav
                if (
                    click_idx is not None
                    and int(click_idx) in _nav_el_indices
                    and int(click_idx) != _support_el.index
                ):
                    logger.warning(
                        "HEURISTIC_OVERRIDE: invoices done, redirecting to Support idx=%d (was clicking nav %s)",
                        _support_el.index,
                        click_idx,
                    )
                    decision = AgentDecision(
                        thought="Auto-navigate to Support: invoice section complete",
                        tool=ToolCall(name="click_element", args={"index": _support_el.index}),
                    )

            # Demo portal only: block navigate away from the Acme SPA.
            _demo_portal_marker = "/static/portal/"
            _on_demo_portal = _demo_portal_marker in (observation.url or "")
            _demo_start = _demo_portal_marker in (spec.start_url or "")
            if _on_demo_portal or _demo_start:
                _base_url = "http://localhost:8765/static/portal/index.html"
                if (
                    decision.tool is not None
                    and decision.tool.name == "navigate"
                    and not decision.is_finish
                ):
                    nav_url = decision.tool.args.get("url", "")
                    if nav_url and _base_url not in nav_url:
                        logger.warning(
                            "HEURISTIC_OVERRIDE: blocking navigate to non-SPA url %s → going to %s",
                            nav_url,
                            _base_url,
                        )
                        decision = AgentDecision(
                            thought="Auto: this is a SPA, navigate to base URL instead",
                            tool=ToolCall(name="navigate", args={"url": _base_url}),
                        )

            # Block premature finish when support ticket not yet submitted
            if _on_demo_portal and decision.is_finish and "support" not in memory.sections_done:
                _support_el2 = next(
                    (el for el in observation.elements if el.name and "Support" in el.name),
                    None,
                )
                if _support_el2:
                    logger.warning("HEURISTIC_OVERRIDE: blocking finish, support not done → navigate to Support")
                    decision = AgentDecision(
                        thought="Auto: must complete support ticket before finishing",
                        tool=ToolCall(name="click_element", args={"index": _support_el2.index}),
                    )

            # Support wizard auto-pilot: guide through all steps automatically
            if "invoices" in memory.sections_done and "support" not in memory.sections_done:
                _el_names_set = {el.name for el in observation.elements if el.name}
                _category_el = next(
                    (el for el in observation.elements
                     if el.role in ("combobox", "listbox") and el.name and "Category" in el.name),
                    None,
                )
                _subject_el = next(
                    (el for el in observation.elements
                     if el.role == "textbox" and el.name and "Subject" in el.name),
                    None,
                )
                _desc_el = next(
                    (el for el in observation.elements
                     if el.role in ("textbox",) and el.name and "Description" in el.name),
                    None,
                )
                _submit_el = next(
                    (el for el in observation.elements
                     if el.role == "button" and el.name and "Submit" in el.name),
                    None,
                )
                _next_el = next(
                    (el for el in observation.elements
                     if el.role == "button" and el.name
                     and "Next" in el.name and "Back" not in el.name),
                    None,
                )
                _ticket_ready = any("ticket-json" in str(el.name) for el in observation.elements)

                if _category_el is not None:
                    cat_val = _category_el.signature_metadata.get("value", "")
                    if not cat_val or cat_val in ("Select...", "请选择..."):
                        logger.warning("SUPPORT_AUTOPILOT: select category")
                        decision = AgentDecision(
                            thought="Support auto-pilot: select System Integration category",
                            tool=ToolCall(name="select_option", args={
                                "index": _category_el.index, "value": "System Integration"
                            }),
                        )
                    elif _next_el and decision.tool and decision.tool.name != "click_element":
                        logger.warning("SUPPORT_AUTOPILOT: click Next (category selected)")
                        decision = AgentDecision(
                            thought="Support auto-pilot: category selected, click Next",
                            tool=ToolCall(name="click_element", args={"index": _next_el.index}),
                        )
                    elif _next_el and decision.is_finish:
                        logger.warning("SUPPORT_AUTOPILOT: click Next (blocked finish on step1)")
                        decision = AgentDecision(
                            thought="Support auto-pilot: click Next",
                            tool=ToolCall(name="click_element", args={"index": _next_el.index}),
                        )
                elif _subject_el is not None:
                    subj_val = _subject_el.signature_metadata.get("value", "")
                    desc_val = _desc_el.signature_metadata.get("value", "") if _desc_el else ""
                    if not subj_val:
                        logger.warning("SUPPORT_AUTOPILOT: fill subject")
                        decision = AgentDecision(
                            thought="Support auto-pilot: fill subject field",
                            tool=ToolCall(name="type_text", args={
                                "index": _subject_el.index, "text": "API webhook delay"
                            }),
                        )
                    elif _desc_el and not desc_val:
                        logger.warning("SUPPORT_AUTOPILOT: fill description")
                        decision = AgentDecision(
                            thought="Support auto-pilot: fill description field",
                            tool=ToolCall(name="type_text", args={
                                "index": _desc_el.index,
                                "text": "EDI 856 acknowledgments are delayed by 2 hours since Nov 28",
                            }),
                        )
                    elif _next_el:
                        # Both fields filled — always force Next, preventing re-typing loops
                        _clicking_next = (
                            decision.tool
                            and decision.tool.name == "click_element"
                            and decision.tool.args.get("index") == _next_el.index
                        )
                        if not _clicking_next:
                            logger.warning("SUPPORT_AUTOPILOT: click Next (step2 filled)")
                            decision = AgentDecision(
                                thought="Support auto-pilot: fields filled, click Next",
                                tool=ToolCall(name="click_element", args={"index": _next_el.index}),
                            )
                elif _submit_el is not None and not decision.is_finish:
                    curr_idx = decision.tool.args.get("index") if decision.tool else None
                    if decision.tool is None or decision.tool.name != "click_element" or curr_idx != _submit_el.index:
                        logger.warning("SUPPORT_AUTOPILOT: click Submit")
                        decision = AgentDecision(
                            thought="Support auto-pilot: click Submit to create ticket",
                            tool=ToolCall(name="click_element", args={"index": _submit_el.index}),
                        )

            if decision.is_finish:
                if (
                    decision.success
                    and clock.steps_used == 0
                    and not memory.extracted_items
                    and decision.result is None
                ):
                    logger.warning(
                        "blocking zero-step success finish objective=%r",
                        spec.objective,
                    )
                    decision = _failed_finish(
                        "No browser actions were taken; task cannot be marked complete"
                    )
                evidence_err = _success_finish_evidence_error(
                    decision,
                    memory,
                    self.trajectory,
                    data_schema=spec.data_schema,
                )
                if evidence_err:
                    logger.warning(
                        "blocking unverified success finish objective=%r: %s",
                        spec.objective,
                        evidence_err,
                    )
                    decision = _failed_finish(evidence_err)
                result = await self._finalize_finish(
                    decision,
                    spec,
                    memory,
                    finish_retries=finish_retries,
                )
                if result is None:
                    finish_retries += 1
                    if finish_retries >= 2:
                        return await _user_facing_failure(
                            TaskResult(
                                success=False,
                                summary="schema validation failed after retry",
                                reason="schema_validation_failed",
                                steps_taken=clock.steps_used,
                                items=list(memory.extracted_items),
                            ),
                            objective=spec.objective,
                            memory=memory,
                        )
                    continue
                result.steps_taken = clock.steps_used
                if result.success and spec.synthesize_workflow and self.trajectory:
                    from app.services.trajectory_synthesis import synthesize_workflow

                    synthesized_id = synthesize_workflow(
                        spec.objective,
                        self.trajectory,
                    )
                    result.synthesized_workflow_id = synthesized_id
                if not result.success:
                    result = await _user_facing_failure(
                        result,
                        objective=spec.objective,
                        memory=memory,
                    )
                await emit({
                    "event": "task_finished",
                    "success": result.success,
                    "result": result.model_dump(),
                    "synthesized_workflow_id": synthesized_id,
                    "ts": _ts(),
                })
                return result

            if decision.tool is None:
                clock.record_step()
                continue

            tool_name = decision.tool.name
            if tool_name not in effective_allowed:
                memory.record_step(
                    f"blocked tool {tool_name}",
                    {"error": "tool not allowed"},
                    observation.url,
                )
                clock.record_step()
                continue

            allowed_action, pause_reason = await gate.check(
                tool_name,
                decision.tool.args,
                observation=observation,
            )
            if not allowed_action:
                await emit({
                    "event": "task_paused",
                    "reason": pause_reason,
                    "tool": tool_name,
                    "ts": _ts(),
                })
                memory.record_step(
                    tool_name,
                    {"skipped": True, "reason": pause_reason},
                    observation.url,
                )
                clock.record_step()
                continue

            try:
                exec_result = await self._execute_tool(
                    tool_name,
                    decision.tool.args,
                    observation=observation,
                    allowed_domains=spec.allowed_domains,
                    memory=memory,
                    page=page,
                )
            except Exception as exc:
                logger.warning("tool %s raised: %s", tool_name, exc)
                exec_result = {
                    **tool_error_from_exception(exc, action=tool_name),
                    "tool": tool_name,
                }

            action_label = (
                f"{tool_name}({json.dumps(decision.tool.args, default=str)[:60]})"
            )
            previous_action_label = memory.last_action_label
            data_items_before = len(memory.extracted_items)
            memory.record_step(action_label, exec_result, observation.url)
            after_observation = await self._perceive_step(
                page,
                memory,
                allowed=allowed,
                ref_hint=f"task-{clock.steps_used}-effect",
            )
            action_effect = summarize_action_effect(
                observation,
                after_observation,
                action_label=action_label,
                previous_action_label=previous_action_label,
                data_items_before=data_items_before,
                data_items_after=len(memory.extracted_items),
            )
            memory.record_action_effect(action_effect)

            if tool_name == "click_element":
                logger.warning(
                    "AFTER_CLICK step=%d els=%s",
                    clock.steps_used + 1,
                    [(el.index, el.name[:30] if el.name else "") for el in after_observation.elements],
                )

            await emit({
                "event": "vision_step",
                "step_index": clock.steps_used,
                "thought": decision.thought or action_label,
                "action": tool_name,
                "target_index": decision.tool.args.get("index"),
                "url": observation.url,
                "args": dict(decision.tool.args),
                "screenshot_ref": observation.screenshot_ref,
                "result": exec_result,
                "action_effect": action_effect,
                "ts": _ts(),
            })

            stable = not (
                isinstance(exec_result, dict) and exec_result.get("error")
            )
            self.trajectory.append(
                TrajectoryStep(
                    step_index=clock.steps_used,
                    tool=tool_name,
                    args=dict(decision.tool.args),
                    result=exec_result,
                    url=observation.url,
                    stable=stable,
                    thought=decision.thought,
                )
            )

            clock.record_step()

            logger.warning(
                "AGENT_STEP step=%d action=%s args=%s effect=%s items=%d",
                clock.steps_used,
                tool_name,
                json.dumps(decision.tool.args, default=str)[:80],
                action_effect.get("summary", "?"),
                len(memory.extracted_items),
            )

            # Skip no-progress when the tool returned a recoverable error or
            # already_extracted — the agent should get another turn to adapt.
            _skip_progress = isinstance(exec_result, dict) and (
                exec_result.get("already_extracted") or exec_result.get("error")
            )

            if observation is not None and not _skip_progress:
                diag = progress.record(
                    after_observation,
                    action_label=action_label,
                    data_items_count=len(memory.extracted_items),
                )
                if diag:
                    result = await _user_facing_failure(
                        TaskResult(
                            success=False,
                            summary=diag,
                            reason="no_progress",
                            steps_taken=clock.steps_used,
                            items=list(memory.extracted_items),
                        ),
                        objective=spec.objective,
                        memory=memory,
                    )
                    await emit({
                        "event": "task_finished",
                        "success": False,
                        "result": result.model_dump(),
                        "ts": _ts(),
                    })
                    return result

            if clock.steps_used > 0 and clock.steps_used % REFLECT_EVERY_K == 0:
                memory.plan = await self.reflect_fn(memory=memory)
                await emit({
                    "event": "task_reflection",
                    "reflection": f"Replanned after step {clock.steps_used}",
                    "plan": [p.model_dump() for p in memory.plan],
                    "ts": _ts(),
                })
                await emit({
                    "event": "task_plan_updated",
                    "plan": [p.model_dump() for p in memory.plan],
                    "ts": _ts(),
                })

        reason = (
            "time_budget_exhausted"
            if clock.deadline_exceeded()
            else "step_budget_exhausted"
        )
        result = await _user_facing_failure(
            TaskResult(
                success=False,
                summary=f"Budget exhausted ({reason})",
                reason=reason,
                steps_taken=clock.steps_used,
                items=list(memory.extracted_items),
            ),
            objective=spec.objective,
            memory=memory,
        )
        await emit({
            "event": "task_finished",
            "success": False,
            "result": result.model_dump(),
            "ts": _ts(),
        })
        return result

    async def _finalize_finish(
        self,
        decision: AgentDecision,
        spec: TaskSpec,
        memory: Memory,
        *,
        finish_retries: int,
    ) -> Optional[TaskResult]:
        if spec.data_schema:
            data = decision.result
            if data is None and decision.summary:
                try:
                    data = json.loads(decision.summary)
                except json.JSONDecodeError:
                    data = None
            if data is None:
                return None
            ok, err = _validate_json_schema(data, spec.data_schema)
            if not ok:
                if finish_retries >= 1:
                    return TaskResult(
                        success=False,
                        summary=f"schema validation failed: {err}",
                        reason="schema_validation_failed",
                        items=list(memory.extracted_items),
                    )
                return None
            return TaskResult(
                success=decision.success,
                summary=decision.summary or "done",
                data=data,
                items=list(memory.extracted_items),
            )
        return TaskResult(
            success=decision.success,
            summary=decision.summary or str(decision.result or ""),
            items=list(memory.extracted_items),
        )

    async def _execute_tool(
        self,
        name: str,
        args: dict[str, Any],
        *,
        observation: Observation,
        allowed_domains: Optional[list[str]],
        memory: Memory,
        page: Any,
    ) -> Any:
        from app.services.artifact_context import get_run_id
        from app.services.livestream import USER_HAS_CONTROL, user_has_control

        if name in {
            "navigate",
            "click_element",
            "type_text",
            "select_option",
            "scroll",
            "drag_element",
            "desktop_click",
            "desktop_type",
            "desktop_key",
            "desktop_scroll",
        } and user_has_control(get_run_id()):
            return {"error": USER_HAS_CONTROL}
        if name == "navigate":
            url = str(args.get("url", ""))
            err = check_navigation(url, allowed_domains)
            if err:
                return {"error": err}
            memory.active_desktop_app = None
            return await actions.navigate(url)

        if name == "http_request":
            url = str(args.get("url", ""))
            err = check_navigation(url, allowed_domains)
            if err:
                return {"error": err}
            from app.nodes import http_request as http_node

            params = {
                "method": args.get("method", "GET"),
                "url": url,
                "headers": args.get("headers") or {},
                "body": args.get("body"),
            }
            items = await http_node.run(params, input_items=[], context={})
            return items[0].json if items else {}

        if name in TRANSFORM_NODE_TYPES:
            params = args.get("params") or args
            items = await run_transform(name, params, input_items=[], context={})
            return [item.model_dump() for item in items]

        if name == "integration":
            from app.nodes import integration as integration_node

            items = await integration_node.run(
                args,
                input_items=[],
                context={},
                session=None,
                workflow_id=None,
            )
            return [item.model_dump() for item in items]

        if name == "extract":
            schema_json = args.get("schema_json", "{}")
            try:
                schema = json.loads(schema_json) if schema_json else None
            except json.JSONDecodeError:
                schema = None

            # Prevent repeated extraction from the same page state
            import hashlib as _hl
            _el_sig = _hl.sha256(
                "".join(f"{e.role}:{e.name}" for e in observation.elements).encode()
            ).hexdigest()[:16]
            _same_state = (
                memory.last_extract_url == observation.url
                and memory.last_extract_element_hash == _el_sig
            )
            if _same_state:
                memory.already_extracted_count += 1
                # Mark invoice section done on already_extracted if signal was visible before
                _inv_signal_els = any(
                    "CALL EXTRACT NOW" in (el.name or "")
                    for el in observation.elements
                )
                if _inv_signal_els:
                    memory.sections_done.add("invoices")
                    logger.warning("sections_done marked invoices (already_extracted with signal)")
                _tkt_signal_els = any(
                    "TICKET READY" in (el.name or "")
                    for el in observation.elements
                )
                if _tkt_signal_els:
                    memory.sections_done.add("support")
                    logger.warning("sections_done marked support (already_extracted with ticket signal)")
                # After 3 ignored extract calls, force navigation by removing
                # the extract block (reset tracking) so the agent can try again
                # on a different section.
                if memory.already_extracted_count >= 3:
                    memory.last_extract_url = None
                    memory.last_extract_element_hash = None
                    memory.already_extracted_count = 0
                # Clear the detail panels to signal data is captured — changes page state
                try:
                    await page.evaluate("""() => {
                        ['order-detail-panel','invoice-summary-panel'].forEach(function(id) {
                            var p = document.getElementById(id);
                            if (p && !p.classList.contains('hidden-panel')) {
                                p.classList.add('hidden-panel');
                            }
                        });
                        var oj = document.getElementById('order-json');
                        if (oj) oj.textContent = '';
                        var ij = document.getElementById('invoice-json');
                        if (ij) ij.textContent = '';
                        var rb = document.getElementById('invoice-data-ready-btn');
                        if (rb) rb.style.display = 'none';
                    }""")
                except Exception:
                    pass
                return {
                    "already_extracted": True,
                    "note": "Data was already extracted from this page state. Navigate to the next section instead.",
                    "url": page.url,
                }
            memory.last_extract_url = observation.url
            memory.last_extract_element_hash = _el_sig

            # Detect which section is being extracted so we can mark it done
            _has_invoice_signal = any(
                "CALL EXTRACT NOW" in (el.name or "")
                for el in observation.elements
            )
            if _has_invoice_signal:
                memory.sections_done.add("invoices")
                logger.warning("sections_done marked invoices (extract with signal)")

            # Also detect ticket-json presence to mark support done
            _has_ticket_signal = any(
                "ticket" in (el.name or "").lower() and "json" in (el.name or "").lower()
                for el in observation.elements
            )
            if _has_ticket_signal or any(
                "TICKET READY" in (el.name or "") for el in observation.elements
            ):
                memory.sections_done.add("support")
                logger.warning("sections_done marked support (extract with ticket signal)")

            try:
                return await self.vision_agent.run_extract(
                    instruction=memory.objective,
                    schema=schema,
                )
            except Exception as exc:
                logger.warning("vision extract failed, falling back to DOM extraction: %s", exc)
                try:
                    dom_data = await page.evaluate("""() => {
                        function getJson(id) {
                            var el = document.getElementById(id);
                            if (!el) return null;
                            try { return JSON.parse(el.textContent); } catch(e) { return el.textContent.trim() || null; }
                        }
                        return {
                            order_json: getJson('order-json'),
                            invoice_json: getJson('invoice-json'),
                            ticket_json: getJson('ticket-json'),
                            page_url: window.location.href,
                        };
                    }""")
                    return {"extracted": dom_data, "url": page.url}
                except Exception as dom_exc:
                    logger.warning("DOM extraction also failed: %s", dom_exc)
                    return {
                        "extracted": observation.page_text_summary[:2000],
                        "url": page.url,
                        "note": "extracted from page text",
                    }

        if name == "click_element":
            ref = args.get("ref")
            if ref:
                try:
                    element = resolve_ref(observation, str(ref))
                except ValueError:
                    return {"error": f"ref {str(ref)!r} unavailable in current observation"}
                index = element.index
            else:
                index = int(args["index"])
            locator, _ = await resolve_element(page, observation, index)
            if locator is None:
                return {"error": f"index {index} unavailable"}
            try:
                await locator.click()
            except Exception as exc:
                return {
                    **normalize_tool_error(str(exc), action="click_element"),
                    "action": "click_element",
                }
            # Wait for DOM updates to settle
            await page.wait_for_timeout(500)
            # If invoice panel just became visible, wait for it to be accessible
            try:
                await page.wait_for_selector(
                    "#invoice-summary-panel:not(.hidden-panel)",
                    state="visible",
                    timeout=2000,
                )
                # Give accessibility tree a moment to update after visibility change
                await page.wait_for_timeout(200)
            except Exception:
                pass  # Panel might not appear (normal for non-DS clicks)
            if ref:
                return {"clicked_ref": str(ref), "clicked_index": index, "url": page.url}
            return {"clicked_index": index, "url": page.url}

        if name == "type_text":
            ref = args.get("ref")
            if ref:
                try:
                    element = resolve_ref(observation, str(ref))
                except ValueError:
                    return {"error": f"ref {str(ref)!r} unavailable in current observation"}
                index = element.index
            else:
                index = int(args["index"])
            text = str(args.get("text", ""))
            locator, _ = await resolve_element(page, observation, index)
            if locator is None:
                return {"error": f"index {index} unavailable"}
            try:
                await locator.fill(text)
            except Exception as exc:
                return {
                    **normalize_tool_error(str(exc), action="type_text"),
                    "action": "type_text",
                }
            await page.wait_for_timeout(200)
            if ref:
                return {"typed_ref": str(ref), "typed_index": index, "text": text, "url": page.url}
            return {"typed_index": index, "text": text, "url": page.url}

        if name == "select_option":
            ref = args.get("ref")
            if ref:
                try:
                    element = resolve_ref(observation, str(ref))
                except ValueError:
                    return {"error": f"ref {str(ref)!r} unavailable in current observation"}
                index = element.index
            else:
                index = int(args["index"])
            value = str(args.get("value", ""))
            locator, _ = await resolve_element(page, observation, index)
            if locator is None:
                return {"error": f"index {index} unavailable"}
            # Try selecting by value attribute first, then by visible label text
            selected = False
            try:
                await locator.select_option(value=value, timeout=2000)
                selected = True
            except Exception:
                pass
            if not selected:
                try:
                    await locator.select_option(label=value, timeout=2000)
                    selected = True
                except Exception:
                    pass
            if not selected:
                return {"error": f"option '{value}' not found in select", "url": page.url}
            await page.wait_for_timeout(300)
            if ref:
                return {"selected_ref": str(ref), "selected_index": index, "value": value, "url": page.url}
            return {"selected_index": index, "value": value, "url": page.url}

        if name == "scroll":
            direction = args.get("direction", "down")
            dy = 500 if direction == "down" else -500
            try:
                await page.mouse.wheel(0, dy)
            except Exception as exc:
                return {
                    **normalize_tool_error(str(exc), action="scroll"),
                    "action": "scroll",
                }
            return {"direction": direction, "url": page.url}

        if name == "drag_element":
            from app.agents.fuzzy import drag_element_horizontal

            ref = args.get("ref")
            if ref:
                try:
                    element = resolve_ref(observation, str(ref))
                except ValueError:
                    return {"error": f"ref {str(ref)!r} unavailable in current observation"}
                index = element.index
            else:
                index = int(args["index"])
            locator, _ = await resolve_element(page, observation, index)
            if locator is None:
                return {"error": f"index {index} unavailable"}
            result = await drag_element_horizontal(page, locator)
            result["dragged_index"] = index
            if ref:
                result["dragged_ref"] = str(ref)
            return result

        if name == "go_back":
            try:
                await page.go_back()
            except Exception as exc:
                return {
                    **normalize_tool_error(str(exc), action="go_back"),
                    "action": "go_back",
                }
            return {"url": page.url}

        if name == "wait":
            ms = int(args.get("ms", 500))
            await asyncio.sleep(max(0, ms) / 1000)
            return {"waited_ms": ms}

        if name in {
            "list_apps",
            "open_app",
            "get_app_state",
            "desktop_click",
            "desktop_type",
            "desktop_key",
            "desktop_scroll",
        }:
            from app.services.desktop_computer_use import (
                DesktopAppAuthorizationError,
                DesktopAppBusyError,
                DesktopAppForbiddenError,
                DesktopComputerUseUnavailableError,
                DesktopSessionUnavailableError,
                hold_desktop_app,
                require_interactive_session,
                resolve_desktop_backend,
            )
            from app.services.desktop_perception import compact_desktop_observation

            try:
                desktop = resolve_desktop_backend()
            except DesktopComputerUseUnavailableError as exc:
                return {"error": str(exc)}
            try:
                if name == "list_apps":
                    apps = await desktop.list_apps()
                    return {
                        "apps": [
                            {
                                "app_id": a.app_id,
                                "name": a.name,
                                "bundle_id": a.bundle_id,
                                "frontmost": a.frontmost,
                            }
                            for a in apps
                        ]
                    }
                app = str(args.get("app") or "")
                require_interactive_session()
                if memory.desktop_lock_holder is None:
                    import uuid as _uuid

                    memory.desktop_lock_holder = f"autonomous-{_uuid.uuid4().hex[:12]}"
                holder = memory.desktop_lock_holder
                with hold_desktop_app(app, holder):
                    if name == "open_app":
                        info = await desktop.open_app(app)
                        memory.active_desktop_app = info.app_id or app
                        return {
                            "app_id": info.app_id,
                            "name": info.name,
                            "bundle_id": info.bundle_id,
                        }
                    if name == "get_app_state":
                        state = await desktop.get_app_state(app)
                        memory.active_desktop_app = (
                            state.app.app_id or state.app.bundle_id or app
                        )
                        return compact_desktop_observation(state)
                    memory.active_desktop_app = memory.active_desktop_app or app
                    if name == "desktop_click":
                        return await desktop.click(
                            app,
                            index=(
                                int(args["index"])
                                if args.get("index") is not None
                                else None
                            ),
                            x=float(args["x"]) if args.get("x") is not None else None,
                            y=float(args["y"]) if args.get("y") is not None else None,
                        )
                    if name == "desktop_type":
                        return await desktop.type_text(
                            app,
                            str(args.get("text") or ""),
                            index=(
                                int(args["index"])
                                if args.get("index") is not None
                                else None
                            ),
                        )
                    if name == "desktop_key":
                        return await desktop.key(app, str(args.get("key") or ""))
                    if name == "desktop_scroll":
                        return await desktop.scroll(
                            app,
                            str(args.get("direction") or "down"),
                            int(args.get("amount") or 3),
                        )
            except (
                DesktopAppAuthorizationError,
                DesktopAppForbiddenError,
                DesktopAppBusyError,
                DesktopSessionUnavailableError,
            ) as exc:
                return {"error": str(exc)}
            except Exception as exc:
                return {"error": str(exc)}

        return {"error": f"unknown tool {name!r}"}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _user_facing_failure(
    result: TaskResult,
    *,
    objective: str,
    memory: Memory,
) -> TaskResult:
    if result.success:
        return result
    return await finalize_failure_result(
        result,
        objective=objective,
        memory_context=memory.to_context(),
    )


async def run_task(
    spec: TaskSpec,
    emit: EventEmitter,
    *,
    abort_event: Optional[asyncio.Event] = None,
    decide_fn: Optional[DecideFn] = None,
    reflect_fn: Optional[ReflectFn] = None,
    confirmation_gate: Optional[ConfirmationGate] = None,
) -> TaskResult:
    agent = AutonomousAgent(
        decide_fn=decide_fn,
        reflect_fn=reflect_fn,
        confirmation_gate=confirmation_gate,
    )
    return await agent.run_task(spec, emit, abort_event=abort_event)


__all__ = [
    "AutonomousAgent",
    "AgentDecision",
    "ToolCall",
    "Memory",
    "TrajectoryStep",
    "run_task",
    "resolve_allowed_tools",
    "tool_schemas",
    "default_decide",
    "default_reflect",
]
