from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Literal, Optional

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from sqlmodel import Session

from app.agents.vision import VisionAgent
from app.exec.scheduler import execute_dag
from app.nodes.result import Item, NodeResult
from app.schemas import ApprovalParams, Edge, Node, Workflow
from app.services import variable_interpolation
from app.services.credential_interpolation import CredentialResolutionError
from app.services.variable_interpolation import VariableResolutionError
from app.settings import settings
from app.tools import actions
from app.tools.browser import get_page


def _coerce_result(raw: Any) -> NodeResult:
    """Wrap a node's return into the canonical items envelope.

    Existing actions return a ``dict`` / ``None``; new data nodes may return
    a :class:`NodeResult` or a ``list[Item]`` directly.
    """
    if isinstance(raw, NodeResult):
        return raw
    if isinstance(raw, list) and all(isinstance(x, Item) for x in raw):
        return NodeResult.from_items(raw)
    return NodeResult.single(raw)


logger = logging.getLogger(__name__)


@dataclass
class NodeOutcome:
    kind: Literal["completed", "failed"]
    result: Optional[NodeResult] = None
    error: Optional[BaseException] = None
    attempts: int = 1


class _RunAborted(Exception):
    """Raised when abort is signalled during a retry backoff sleep."""


class _RunRejected(Exception):
    """Raised when an approval node is rejected by the operator."""


_DATA_TRANSFORM_TYPES = frozenset({
    "set",
    "filter",
    "sort",
    "limit",
    "aggregate",
    "split_out",
    "remove_duplicates",
    "rename_keys",
    "datetime",
})

_ACTION_NODE_TYPES = frozenset({
    "http_request",
    "integration",
    "parse_json",
    "parse_csv",
    "read_file",
    "write_file",
    "send_email",
    "validation",
    "text_prompt",
})

_COMPOSITE_NODE_TYPES = frozenset({
    "foreach",
    "subworkflow",
    "while_loop",
})

_ITEMS_NODE_TYPES = _DATA_TRANSFORM_TYPES | _ACTION_NODE_TYPES | _COMPOSITE_NODE_TYPES


EventSender = Callable[[dict], Awaitable[None]]


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_emit(send: EventSender):
    async def emit(event: str, *, node_id: str | None = None, **extra: Any) -> None:
        payload: dict[str, Any] = {"event": event, "node_id": node_id, "ts": _ts()}
        payload.update(extra)
        await send(payload)
        await asyncio.sleep(0)
    return emit


async def _wait_cancellable(ms: int, abort_event: Optional[asyncio.Event]) -> dict:
    if abort_event is None:
        await asyncio.sleep(ms / 1000)
        return {"waited_ms": ms}
    try:
        await asyncio.wait_for(abort_event.wait(), timeout=ms / 1000)
        return {"waited_ms": 0, "aborted": True}
    except asyncio.TimeoutError:
        return {"waited_ms": ms}


_SELECTOR_MISS_HINTS = (
    "no element matches",
    "did not find element",
    "waiting for selector",
    "waiting for locator",
    "expected to find element",
    "element is not attached",
)


def _is_selector_miss(exc: BaseException) -> bool:
    if isinstance(exc, PlaywrightTimeoutError):
        return True
    if isinstance(exc, PlaywrightError):
        msg = str(exc).lower()
        return any(h in msg for h in _SELECTOR_MISS_HINTS)
    return False


def _is_heal_disabled(node: Node, *, session: Optional[Session]) -> bool:
    from app.services.llm_runtime import get_self_heal_settings

    if (node.params or {}).get("auto_heal") is False:
        return True
    try:
        settings_obj = get_self_heal_settings(session)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("self-heal: get_self_heal_settings failed (%s)", exc)
        return False
    return not settings_obj.enabled


def _vision_threshold(session: Optional[Session]) -> float:
    from app.services.llm_runtime import get_self_heal_settings

    try:
        return float(get_self_heal_settings(session).threshold)
    except Exception:
        return 0.6


def _action_verb(node_type: str) -> str:
    if node_type == "click":
        return "click"
    if node_type == "fill":
        return "fill"
    return node_type


def _make_instruction(node: Node, original_selector: str) -> str:
    verb = _action_verb(node.type)
    label = (node.label or "").strip()
    label_part = f" for: {label}" if label else ""
    return (
        f"Find the element to {verb}{label_part}. "
        f"Original selector was: {original_selector!r}."
    )


async def _run_deterministic_action(node_type: str, selector: str, value: str) -> Any:
    if node_type == "click":
        return await actions.click(selector)
    if node_type == "fill":
        return await actions.fill(selector, value)
    raise ValueError(f"unsupported action {node_type!r}")


async def _run_deterministic_action_with_timeout(
    node_type: str, selector: str, value: str, timeout_ms: int
) -> Any:
    page = await get_page()
    locator = page.locator(selector)
    if node_type == "click":
        await locator.click(timeout=timeout_ms)
        return {"selector": selector, "clicked": True}
    if node_type == "fill":
        tag = await locator.evaluate("el => el.tagName.toLowerCase()")
        if tag == "select":
            await locator.select_option(value, timeout=timeout_ms)
        else:
            await locator.fill(value, timeout=timeout_ms)
        return {"selector": selector, "value": value}
    raise ValueError(f"unsupported action {node_type!r}")


def _cache_context_ready(
    session: Optional[Session], workflow_id: Optional[str]
) -> bool:
    return session is not None and workflow_id is not None


async def _current_page_url() -> Optional[str]:
    try:
        page = await get_page()
        return page.url
    except Exception:
        return None


async def _try_cached_selector_action(
    *,
    node: Node,
    node_type: str,
    value: str,
    session: Session,
    workflow_id: str,
    emit,
) -> Optional[Any]:
    from app.services import selector_cache as cache_svc

    if not cache_svc.is_cache_enabled(session):
        return None

    page_url = await _current_page_url()
    if not page_url:
        return None

    p = node.params or {}
    lookup = cache_svc.get_entry(
        session,
        workflow_id=workflow_id,
        node_id=node.id,
        url=page_url,
        node_params=p,
    )
    if lookup is None:
        await emit(
            "cache_miss",
            node_id=node.id,
            url_pattern=cache_svc.normalize_url(page_url, p),
            reason="no_entry",
        )
        return None

    entry = lookup.entry
    if entry.kind != "selector":
        await emit(
            "cache_miss",
            node_id=node.id,
            cache_entry_id=entry.id,
            url_pattern=lookup.url_pattern,
            reason="kind_mismatch",
        )
        return None

    declared = str(p.get("selector", "")).strip()
    if declared and entry.selector != declared:
        await emit(
            "cache_miss",
            node_id=node.id,
            cache_entry_id=entry.id,
            url_pattern=lookup.url_pattern,
            reason="selector_mismatch",
            cached_selector=entry.selector,
            declared_selector=declared,
        )
        return None

    try:
        result = await _run_deterministic_action_with_timeout(
            node_type,
            entry.selector,
            value,
            settings.cache_replay_timeout_ms,
        )
    except Exception as exc:
        if not _is_selector_miss(exc):
            raise
        evicted = cache_svc.record_miss(session, entry)
        await emit(
            "cache_miss",
            node_id=node.id,
            cache_entry_id=entry.id,
            url_pattern=lookup.url_pattern,
            reason="replay_failed",
            evicted=evicted,
        )
        return None

    cache_svc.record_hit(session, entry)
    await emit(
        "cache_hit",
        node_id=node.id,
        cache_entry_id=entry.id,
        url_pattern=lookup.url_pattern,
        selector=entry.selector,
        cost_avoided={"llm_calls": 1, "vision_calls": 0},
    )
    return result


async def _cache_selector_success(
    *,
    session: Optional[Session],
    workflow_id: Optional[str],
    node: Node,
    selector: str,
    confidence: float,
) -> None:
    if not _cache_context_ready(session, workflow_id):
        return
    from app.services import selector_cache as cache_svc

    if not cache_svc.is_cache_enabled(session):
        return
    page_url = await _current_page_url()
    if not page_url:
        return
    cache_svc.upsert_success(
        session,
        workflow_id=workflow_id,
        node_id=node.id,
        url=page_url,
        selector=selector,
        confidence=confidence,
        kind="selector",
        node_params=node.params,
    )


async def _replay_vision_plan(plan: dict[str, Any]) -> dict[str, Any]:
    from app.services.perception import ElementSignature, locator_for_signature

    page = await get_page()
    sig = ElementSignature(role=str(plan["role"]), name=str(plan.get("name", "")))
    locator = await locator_for_signature(page, sig)
    if locator is None:
        raise RuntimeError("cached vision element not found")

    action = str(plan.get("action", "click_element"))
    timeout = settings.cache_replay_timeout_ms
    if action == "click_element":
        await locator.click(timeout=timeout)
        return {"cached": True, "action": action, "url": page.url}
    if action == "type_text":
        await locator.fill(str(plan.get("text", "")), timeout=timeout)
        return {"cached": True, "action": action, "url": page.url}
    raise RuntimeError(f"unsupported cached vision action {action!r}")


async def _try_cached_vision_action(
    *,
    node: Node,
    session: Session,
    workflow_id: str,
    emit,
) -> Optional[Any]:
    from app.services import selector_cache as cache_svc

    if not cache_svc.is_cache_enabled(session):
        return None

    page_url = await _current_page_url()
    if not page_url:
        return None

    p = node.params or {}
    lookup = cache_svc.get_entry(
        session,
        workflow_id=workflow_id,
        node_id=node.id,
        url=page_url,
        node_params=p,
    )
    if lookup is None:
        await emit(
            "cache_miss",
            node_id=node.id,
            url_pattern=cache_svc.normalize_url(page_url, p),
            reason="no_entry",
        )
        return None

    entry = lookup.entry
    if entry.kind != "vision":
        await emit(
            "cache_miss",
            node_id=node.id,
            cache_entry_id=entry.id,
            url_pattern=lookup.url_pattern,
            reason="kind_mismatch",
        )
        return None

    plan = cache_svc.parse_vision_plan(entry)
    if not plan:
        evicted = cache_svc.record_miss(session, entry)
        await emit(
            "cache_miss",
            node_id=node.id,
            cache_entry_id=entry.id,
            url_pattern=lookup.url_pattern,
            reason="invalid_plan",
            evicted=evicted,
        )
        return None

    try:
        result = await _replay_vision_plan(plan)
    except Exception:
        evicted = cache_svc.record_miss(session, entry)
        await emit(
            "cache_miss",
            node_id=node.id,
            cache_entry_id=entry.id,
            url_pattern=lookup.url_pattern,
            reason="replay_failed",
            evicted=evicted,
        )
        return None

    cache_svc.record_hit(session, entry)
    await emit(
        "cache_hit",
        node_id=node.id,
        cache_entry_id=entry.id,
        url_pattern=lookup.url_pattern,
        selector=entry.selector,
        cost_avoided={"llm_calls": 1, "vision_calls": 1},
    )
    return result


async def _cache_vision_success(
    *,
    session: Optional[Session],
    workflow_id: Optional[str],
    node: Node,
    last_step: dict[str, Any],
) -> None:
    if not _cache_context_ready(session, workflow_id) or not last_step:
        return
    from app.services import selector_cache as cache_svc
    from app.services.perception import perceive

    if not cache_svc.is_cache_enabled(session):
        return

    target_index = last_step.get("target_index")
    if target_index is None:
        return

    page_url = await _current_page_url()
    if not page_url:
        return

    page = await get_page()
    obs = await perceive(page, ref_hint="cache-write")
    if target_index < 0 or target_index >= len(obs.elements):
        return

    el = obs.elements[target_index]
    plan = {
        "action": last_step.get("action", "click_element"),
        "role": el.role,
        "name": el.name,
    }
    cache_svc.upsert_success(
        session,
        workflow_id=workflow_id,
        node_id=node.id,
        url=page_url,
        selector=f"{el.role}:{el.name}",
        confidence=1.0,
        kind="vision",
        plan=plan,
        node_params=node.params,
    )

async def _heal_stage(
    *,
    page: Any,
    node: Node,
    original_selector: str,
    mode: Literal["dom", "vision"],
) -> dict:
    from app.agents.selector_finder import propose_selector

    instruction = _make_instruction(node, original_selector)
    return await propose_selector(page=page, instruction=instruction, mode=mode)


async def _try_self_heal(
    *,
    node: Node,
    original_selector: str,
    value: str,
    session: Optional[Session],
    emit,
    workflow_id: Optional[str] = None,
) -> Any:
    """Run the two-stage heal flow. On success returns the action result.

    Re-raises the original Playwright error if no stage produces a usable
    candidate or if the retry with the candidate also fails. Emits exactly
    one `node_self_healed` event per heal attempt — the payload's `mode`
    field identifies which stage produced the recorded `new_selector`."""
    page = await get_page()
    threshold = _vision_threshold(session)

    dom = await _heal_stage(
        page=page, node=node, original_selector=original_selector, mode="dom"
    )
    dom_selector = dom.get("selector")
    dom_conf = float(dom.get("confidence") or 0.0)
    cost = dict(dom.get("cost_hint") or {})

    chosen_mode: Literal["dom", "vision"] = "dom"
    chosen_selector: Optional[str] = dom_selector
    chosen_confidence: float = dom_conf
    last_reasoning: str = str(dom.get("reasoning", ""))

    if dom_selector is None or dom_conf < threshold:
        from app.services.browser_visual import skip_optional_page_screenshots

        if not skip_optional_page_screenshots():
            vision = await _heal_stage(
                page=page,
                node=node,
                original_selector=original_selector,
                mode="vision",
            )
            v_cost = dict(vision.get("cost_hint") or {})
            for key in ("input_tokens", "output_tokens"):
                left = cost.get(key)
                right = v_cost.get(key)
                if left is None and right is None:
                    cost[key] = None
                elif left is None:
                    cost[key] = right
                elif right is None:
                    pass
                else:
                    cost[key] = int(left) + int(right)
            cost["vision_calls"] = int(v_cost.get("vision_calls") or 1)
            chosen_mode = "vision"
            chosen_selector = vision.get("selector")
            chosen_confidence = float(vision.get("confidence") or 0.0)
            last_reasoning = str(vision.get("reasoning", "")) or last_reasoning

    cost.setdefault("input_tokens", None)
    cost.setdefault("output_tokens", None)
    cost.setdefault("vision_calls", 1 if chosen_mode == "vision" else 0)

    if (
        chosen_selector is None
        or chosen_confidence < 0.5
        or not str(chosen_selector).strip()
    ):
        await emit(
            "node_self_healed",
            node_id=node.id,
            mode=chosen_mode,
            old_selector=original_selector,
            new_selector=None,
            confidence=chosen_confidence,
            cost_hint=cost,
        )
        raise RuntimeError(
            f"self-heal could not propose a usable selector "
            f"(confidence={chosen_confidence:.2f}, reasoning={last_reasoning!r})"
        )

    try:
        result = await _run_deterministic_action(node.type, chosen_selector, value)
    except Exception as retry_exc:
        await emit(
            "node_self_healed",
            node_id=node.id,
            mode=chosen_mode,
            old_selector=original_selector,
            new_selector=chosen_selector,
            confidence=chosen_confidence,
            cost_hint=cost,
            post_heal_error=str(retry_exc),
        )
        raise

    await emit(
        "node_self_healed",
        node_id=node.id,
        mode=chosen_mode,
        old_selector=original_selector,
        new_selector=chosen_selector,
        confidence=chosen_confidence,
        cost_hint=cost,
    )
    await _cache_selector_success(
        session=session,
        workflow_id=workflow_id,
        node=node,
        selector=str(chosen_selector),
        confidence=chosen_confidence,
    )
    return result


def _captcha_kwargs(
    emit,
    session: Optional[Session],
    run_id: Optional[str],
    node_id: str,
    abort_event: Optional[asyncio.Event],
) -> dict[str, Any]:
    return {
        "captcha_emit": emit,
        "captcha_run_id": run_id,
        "captcha_node_id": node_id,
        "captcha_abort_event": abort_event,
    }


async def _check_navigation_captcha(
    emit,
    *,
    session: Optional[Session],
    run_id: Optional[str],
    node_id: str,
    abort_event: Optional[asyncio.Event],
) -> None:
    from app.services.captcha.handler import check_navigation_captcha
    from app.tools.browser import get_active_page

    page = get_active_page()
    if page is None:
        return
    await check_navigation_captcha(
        page,
        emit=emit,
        session=session,
        run_id=run_id,
        node_id=node_id,
        abort_event=abort_event,
    )


async def _run_node(
    node: Node,
    emit,
    abort_event: Optional[asyncio.Event] = None,
    session: Optional[Session] = None,
    *,
    context: Optional[dict[str, NodeResult]] = None,
    input_items: Optional[list[Item]] = None,
    workflow_id: Optional[str] = None,
    run_id: Optional[str] = None,
    run_node: Optional[Any] = None,
    totp_identifier: Optional[str] = None,
    params_namespace: Optional[dict[str, Any]] = None,
    trigger_namespace: Optional[dict[str, Any]] = None,
) -> Any:
    t = node.type
    p = node.params or {}
    if t in ("start", "end"):
        return None
    if t == "navigate":
        result = await actions.navigate(str(p["url"]))
        await _check_navigation_captcha(
            emit,
            session=session,
            run_id=run_id,
            node_id=node.id,
            abort_event=abort_event,
        )
        return result
    if t in ("click", "fill"):
        selector = str(p["selector"])
        value = "" if t == "click" else str(p.get("value", ""))

        if _cache_context_ready(session, workflow_id):
            cached = await _try_cached_selector_action(
                node=node,
                node_type=t,
                value=value,
                session=session,
                workflow_id=workflow_id,
                emit=emit,
            )
            if cached is not None:
                return cached

        try:
            result = await _run_deterministic_action(t, selector, value)
        except Exception as exc:
            if not _is_selector_miss(exc):
                raise
            if _is_heal_disabled(node, session=session):
                raise
            if abort_event is not None and abort_event.is_set():
                raise
            try:
                return await _try_self_heal(
                    node=node,
                    original_selector=selector,
                    value=value,
                    session=session,
                    emit=emit,
                    workflow_id=workflow_id,
                )
            except Exception:
                raise exc
        else:
            await _cache_selector_success(
                session=session,
                workflow_id=workflow_id,
                node=node,
                selector=selector,
                confidence=1.0,
            )
            return result
    if t == "wait":
        return await _wait_cancellable(int(p["ms"]), abort_event)
    if t == "extract":
        return await actions.extract(str(p.get("instruction", "")))
    if t in ("vision_navigate", "fuzzy_action"):
        if p.get("action") == "drag_slider":
            from app.agents.fuzzy import drag_slider

            return await drag_slider(
                thumb_selector=str(p.get("thumb_selector", "#slider-thumb")),
                track_selector=str(p.get("track_selector", "#slider-track")),
                min_percent=float(p.get("min_percent", 0.95)),
            )
        if p.get("action") == "drag_puzzle":
            from app.agents.fuzzy import drag_puzzle_captcha

            return await drag_puzzle_captcha(
                thumb_selector=str(p.get("thumb_selector", "#slider-thumb")),
                track_selector=str(p.get("track_selector", "#captcha-track")),
                steps=int(p.get("steps", 30)),
                jitter=bool(p.get("jitter", True)),
            )
        if p.get("action") == "click_recaptcha":
            from app.agents.fuzzy import click_recaptcha_checkbox

            return await click_recaptcha_checkbox()
        agent = VisionAgent()
        goal = str(p.get("goal") or p.get("instruction", ""))
        max_steps = p.get("max_steps")
        success_criteria = p.get("success_criteria")

        async def on_vision_step(step: dict) -> None:
            await emit("vision_step", node_id=node.id, **step)

        async def on_progress(msg: str) -> None:
            await emit("node_progress", node_id=node.id, message=msg)

        return await agent.run_navigate(
            goal=goal,
            max_steps=int(max_steps) if max_steps is not None else None,
            success_criteria=(
                str(success_criteria) if success_criteria is not None else None
            ),
            on_step=on_vision_step,
            on_progress=on_progress,
            session=session,
            workflow_id=workflow_id,
            totp_identifier=totp_identifier,
            **_captcha_kwargs(emit, session, run_id, node.id, abort_event),
        )
    if t == "vision_act":
        agent = VisionAgent()
        last_vision_step: dict[str, Any] = {}

        async def on_vision_step(step: dict) -> None:
            action = step.get("action")
            if action not in ("perceive", "done"):
                last_vision_step.clear()
                last_vision_step.update(step)
            await emit("vision_step", node_id=node.id, **step)

        async def on_progress(msg: str) -> None:
            await emit("node_progress", node_id=node.id, message=msg)

        if _cache_context_ready(session, workflow_id):
            cached = await _try_cached_vision_action(
                node=node,
                session=session,
                workflow_id=workflow_id,
                emit=emit,
            )
            if cached is not None:
                return cached

        result = await agent.run_act(
            instruction=str(p.get("instruction", "")),
            on_step=on_vision_step,
            on_progress=on_progress,
            session=session,
            workflow_id=workflow_id,
            totp_identifier=totp_identifier,
            **_captcha_kwargs(emit, session, run_id, node.id, abort_event),
        )
        if result.get("completed"):
            await _cache_vision_success(
                session=session,
                workflow_id=workflow_id,
                node=node,
                last_step=last_vision_step,
            )
        return result
    if t == "vision_extract":
        agent = VisionAgent()
        schema = p.get("schema")
        if schema is not None and not isinstance(schema, dict):
            schema = None

        async def on_vision_step(step: dict) -> None:
            await emit("vision_step", node_id=node.id, **step)

        async def on_progress(msg: str) -> None:
            await emit("node_progress", node_id=node.id, message=msg)

        result = await agent.run_extract(
            instruction=str(p.get("instruction", "")),
            schema=schema,
            on_step=on_vision_step,
            on_progress=on_progress,
            session=session,
            workflow_id=workflow_id,
            totp_identifier=totp_identifier,
            **_captcha_kwargs(emit, session, run_id, node.id, abort_event),
        )
        if result.get("completed") is False:
            reason = result.get("reason") or "vision_extract_failed"
            raise RuntimeError(f"vision_extract failed: {reason}")
        return result
    if t == "condition":
        from app.services.flow_conditions import (
            FlowConditionError,
            build_flow_namespace,
            evaluate_condition,
        )

        ns = build_flow_namespace(
            context=context,
            input_items=input_items,
            params_namespace=params_namespace,
            trigger_namespace=trigger_namespace,
        )
        try:
            return evaluate_condition(p, namespace=ns)
        except FlowConditionError as exc:
            raise RuntimeError(str(exc)) from exc
    if t == "switch":
        from app.services.flow_conditions import (
            FlowConditionError,
            build_flow_namespace,
            evaluate_switch_case,
        )

        ns = build_flow_namespace(
            context=context,
            input_items=input_items,
            params_namespace=params_namespace,
            trigger_namespace=trigger_namespace,
        )
        try:
            return {"switch_case": evaluate_switch_case(p, namespace=ns)}
        except FlowConditionError as exc:
            raise RuntimeError(str(exc)) from exc
    if t in _DATA_TRANSFORM_TYPES:
        from app.nodes import aggregate, datetime as datetime_node
        from app.nodes import filter as filter_node
        from app.nodes import limit as limit_node
        from app.nodes import remove_duplicates, rename_keys, set, sort, split_out

        dispatch = {
            "set": set.run,
            "filter": filter_node.run,
            "sort": sort.run,
            "limit": limit_node.run,
            "aggregate": aggregate.run,
            "split_out": split_out.run,
            "remove_duplicates": remove_duplicates.run,
            "rename_keys": rename_keys.run,
            "datetime": datetime_node.run,
        }
        items = input_items or []
        ctx = context or {}
        return await dispatch[t](p, input_items=items, context=ctx)
    if t == "http_request":
        from app.nodes import http_request as http_request_node

        return await http_request_node.run(
            p, input_items=input_items or [], context=context or {}
        )
    if t == "integration":
        from app.nodes import integration as integration_node

        return await integration_node.run(
            p,
            input_items=input_items or [],
            context=context or {},
            session=session,
            workflow_id=workflow_id,
        )
    if t == "parse_json":
        from app.nodes import parse_json as parse_json_node

        return await parse_json_node.run(
            p, input_items=input_items or [], context=context or {}
        )
    if t == "parse_csv":
        from app.nodes import parse_csv as parse_csv_node

        return await parse_csv_node.run(
            p, input_items=input_items or [], context=context or {}
        )
    if t == "read_file":
        from app.nodes import read_file as read_file_node

        return await read_file_node.run(
            p,
            input_items=input_items or [],
            context=context or {},
            workflow_id=workflow_id,
        )
    if t == "write_file":
        from app.nodes import write_file as write_file_node

        return await write_file_node.run(
            p,
            input_items=input_items or [],
            context=context or {},
            workflow_id=workflow_id,
        )
    if t == "send_email":
        from app.nodes import send_email as send_email_node

        return await send_email_node.run(
            p,
            input_items=input_items or [],
            context=context or {},
            workflow_id=workflow_id,
            session=session,
        )
    if t == "foreach":
        from app.nodes import foreach as foreach_node

        return await foreach_node.run(
            p,
            input_items=input_items or [],
            context=context or {},
            node_id=node.id,
            emit=emit,
            abort_event=abort_event,
            session=session,
            workflow_id=workflow_id,
            run_id=run_id,
            run_node=run_node,
        )
    if t == "subworkflow":
        from app.nodes import subworkflow as subworkflow_node

        return await subworkflow_node.run(
            p,
            input_items=input_items or [],
            context=context or {},
            node_id=node.id,
            emit=emit,
            abort_event=abort_event,
            session=session,
            workflow_id=workflow_id,
            run_id=run_id,
        )
    if t == "validation":
        from app.nodes import validation as validation_node

        return await validation_node.run(
            p, input_items=input_items or [], context=context or {}
        )
    if t == "text_prompt":
        from app.nodes import text_prompt as text_prompt_node

        return await text_prompt_node.run(
            p, input_items=input_items or [], context=context or {}
        )
    if t == "while_loop":
        from app.nodes import while_loop as while_loop_node

        return await while_loop_node.run(
            p,
            input_items=input_items or [],
            context=context or {},
            node_id=node.id,
            emit=emit,
            abort_event=abort_event,
            session=session,
            workflow_id=workflow_id,
            run_id=run_id,
            run_node=run_node,
        )
    if t == "goto_url":
        from app.nodes import goto_url as goto_url_node

        result = await goto_url_node.run(p)
        await _check_navigation_captcha(
            emit,
            session=session,
            run_id=run_id,
            node_id=node.id,
            abort_event=abort_event,
        )
        return result
    if t == "print_page":
        from app.nodes import print_page as print_page_node

        return await print_page_node.run(p, node_id=node.id)
    if t == "file_upload":
        from app.nodes import file_upload as file_upload_node

        return await file_upload_node.run(
            p,
            workflow_id=workflow_id,
        )
    if t == "file_download":
        from app.nodes import file_download as file_download_node

        return await file_download_node.run(p, node_id=node.id)
    if t == "login":
        from app.nodes import login as login_node

        return await login_node.run(
            p,
            node_id=node.id,
            emit=emit,
            session=session,
            workflow_id=workflow_id,
            run_id=run_id,
            abort_event=abort_event,
            totp_identifier=totp_identifier,
        )
    raise ValueError(f"Unknown node type: {t}")


async def _retry_backoff_ms(
    ms: int, abort_event: Optional[asyncio.Event]
) -> None:
    if ms <= 0:
        return
    if abort_event is None:
        await asyncio.sleep(ms / 1000)
        return
    if abort_event.is_set():
        raise _RunAborted()
    try:
        await asyncio.wait_for(abort_event.wait(), timeout=ms / 1000)
        raise _RunAborted()
    except asyncio.TimeoutError:
        return


async def _invoke_node(
    node: Node,
    emit,
    *,
    abort_event: Optional[asyncio.Event] = None,
    session: Optional[Session] = None,
    context: Optional[dict[str, NodeResult]] = None,
    input_items: Optional[list[Item]] = None,
    workflow_id: Optional[str] = None,
    run_id: Optional[str] = None,
    run_node: Optional[Any] = None,
    trigger_namespace: Optional[dict[str, Any]] = None,
    params_namespace: Optional[dict[str, Any]] = None,
    totp_identifier: Optional[str] = None,
) -> NodeOutcome:
    """Resolve params once, run the action with optional retries, return outcome."""
    resolved = node
    if node.params:
        try:
            resolved_params = variable_interpolation.resolve_params(
                node.params,
                context=context or {},
                session=session,
                workflow_id=workflow_id,
                input_items=input_items,
                trigger_namespace=trigger_namespace,
                params_namespace=params_namespace,
                resolve_expressions=(node.type not in _DATA_TRANSFORM_TYPES),
            )
        except (CredentialResolutionError, VariableResolutionError) as exc:
            return NodeOutcome(kind="failed", error=exc, attempts=1)
        resolved = node.model_copy(update={"params": resolved_params})

    max_attempts = node.retry.max_attempts if node.retry is not None else 1
    last_exc: Optional[BaseException] = None

    for attempt in range(1, max_attempts + 1):
        if abort_event is not None and abort_event.is_set():
            raise _RunAborted()
        try:
            from app.services import artifact_context

            artifact_context.set_run_context(run_id, node_id=node.id)
            raw = await _run_node(
                resolved,
                emit,
                abort_event=abort_event,
                session=session,
                context=context,
                input_items=input_items,
                workflow_id=workflow_id,
                run_id=run_id,
                run_node=run_node,
                totp_identifier=totp_identifier,
                params_namespace=params_namespace,
                trigger_namespace=trigger_namespace,
            )
            return NodeOutcome(
                kind="completed",
                result=_coerce_result(raw),
                attempts=attempt,
            )
        except _RunAborted:
            raise
        except Exception as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break
            delay_ms = (node.retry.backoff_ms if node.retry else 0) * attempt
            next_at = datetime.now(timezone.utc) + timedelta(milliseconds=delay_ms)
            await emit(
                "node_retry",
                node_id=node.id,
                attempt=attempt,
                error=str(exc),
                error_kind=type(exc).__name__,
                next_attempt_at=next_at.isoformat(),
            )
            if abort_event is not None and abort_event.is_set():
                raise _RunAborted()
            await _retry_backoff_ms(delay_ms, abort_event)

    assert last_exc is not None
    return NodeOutcome(kind="failed", error=last_exc, attempts=max_attempts)


def _error_context_entry(exc: BaseException, attempts: int) -> NodeResult:
    return NodeResult.single({
        "error": {
            "message": str(exc),
            "kind": type(exc).__name__,
            "attempts": attempts,
        }
    })


def _pick_next_edge(node: Node, outgoing: list[Edge], result: Any) -> Edge | None:
    if not outgoing:
        return None
    if node.type == "condition":
        branch = "true" if (isinstance(result, dict) and result.get("condition")) else "false"
        for edge in outgoing:
            if edge.when == branch:
                return edge
        for edge in outgoing:
            if edge.when is None:
                return edge
        return outgoing[0]
    return outgoing[0]


def _merge_result(
    node: Node, selected_parents: list[tuple[Edge, NodeResult]]
) -> NodeResult:
    """Combine arrived (non-pruned) parents' items per the merge mode.

    ``selected_parents`` is ordered by incoming-edge order. Pruned/skipped
    parents are simply absent, so a merge of a skipped branch yields the live
    branch without deadlocking.
    """
    params = node.params or {}
    mode = params.get("mode", "append")

    if mode == "wait_all":
        out: dict[str, Any] = {edge.source: res.output for edge, res in selected_parents}
        return NodeResult.from_items([Item(json=out)])

    if mode == "merge_by_key":
        key = params.get("key")
        merged: dict[Any, dict[str, Any]] = {}
        order: list[Any] = []
        for _, res in selected_parents:
            for it in res.items:
                k = it.json.get(key) if isinstance(it.json, dict) else None
                if k in merged:
                    merged[k].update(it.json)
                else:
                    merged[k] = dict(it.json)
                    order.append(k)
        items = [Item(json=merged[k]) for k in order]
        return NodeResult.from_items(items or [Item(json={})])

    if mode == "pass_through":
        if selected_parents:
            items = list(selected_parents[0][1].items)
            return NodeResult.from_items(items or [Item(json={})])
        return NodeResult.from_items([Item(json={})])

    # Default: append — concatenate all parents' items in edge order.
    items = []
    for _, res in selected_parents:
        items.extend(res.items)
    return NodeResult.from_items(items or [Item(json={})])


async def _handle_approval_node(
    node: Node,
    emit,
    *,
    run_id: str,
    workflow_id: Optional[str],
    abort_event: Optional[asyncio.Event],
    session: Optional[Session],
) -> NodeResult:
    from app.services import approvals as approvals_svc
    from app.services import notifications

    if session is None:
        raise ValueError("approval node requires a database session")

    params = ApprovalParams.model_validate(node.params or {})
    inputs_schema = [s.model_dump() for s in params.inputs]
    approval = approvals_svc.request(
        session,
        run_id=run_id,
        node_id=node.id,
        prompt=params.prompt,
        inputs_schema=inputs_schema,
    )
    await emit(
        "node_awaiting_approval",
        node_id=node.id,
        prompt=approval.prompt,
        inputs_schema=approval.inputs_schema,
    )
    from app.services import runs as run_svc

    await run_svc.on_approval_pause(run_id)
    await notifications.emit(
        "approval_requested",
        {
            "run_id": run_id,
            "workflow_id": workflow_id,
            "node_id": node.id,
            "prompt": params.prompt,
        },
    )
    try:
        resolved = await approvals_svc.wait(approval.id, abort_event=abort_event)
    except approvals_svc.ApprovalWaitAborted:
        raise _RunAborted()

    await run_svc.on_approval_resume(run_id)

    decision_inputs = dict(resolved.decision_inputs or {})
    output = {"decision": resolved.decision, "inputs": decision_inputs}

    if resolved.decision == "lost":
        raise RuntimeError("approval lost across backend restart")

    if resolved.decision == "reject":
        await emit("node_rejected", node_id=node.id, output=output)
        raise _RunRejected()

    await emit(
        "node_approved",
        node_id=node.id,
        decision="approve",
        inputs=decision_inputs,
    )
    return NodeResult.single({"decision": "approve", "inputs": decision_inputs})


async def run_workflow(
    workflow: Workflow,
    on_event: EventSender,
    *,
    abort_event: Optional[asyncio.Event] = None,
    session: Optional[Session] = None,
    workflow_id: Optional[str] = None,
    run_id: Optional[str] = None,
    initial_context: Optional[dict[str, NodeResult]] = None,
    trigger_namespace: Optional[dict[str, Any]] = None,
    params_namespace: Optional[dict[str, Any]] = None,
    totp_identifier: Optional[str] = None,
) -> None:
    emit = _make_emit(on_event)

    async def run_node(
        node: Node,
        emit_fn,
        *,
        input_items: list[Item],
        context: dict[str, NodeResult],
        session: Optional[Session] = None,
        workflow_id: Optional[str] = None,
        abort_event: Optional[asyncio.Event] = None,
    ) -> NodeOutcome:
        return await _invoke_node(
            node,
            emit_fn,
            abort_event=abort_event,
            session=session,
            context=context,
            input_items=input_items,
            workflow_id=workflow_id,
            run_id=run_id,
            run_node=run_node,
            trigger_namespace=trigger_namespace,
            params_namespace=params_namespace,
            totp_identifier=totp_identifier,
        )

    await emit("run_started")
    try:
        await execute_dag(
            workflow,
            emit,
            run_node=run_node,
            abort_event=abort_event,
            session=session,
            workflow_id=workflow_id,
            run_id=run_id,
            initial_context=initial_context,
        )
    except _RunAborted:
        await emit("run_aborted")
    except Exception as exc:
        await emit("run_failed", error=str(exc))
