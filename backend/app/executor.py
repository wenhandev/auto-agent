from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Literal, Optional

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from sqlmodel import Session

from app.agents.fuzzy import FuzzyAgent
from app.schemas import Edge, Node, Workflow
from app.services.credential_interpolation import (
    CredentialResolutionError,
    resolve_params,
)
from app.tools import actions
from app.tools.browser import get_page


logger = logging.getLogger(__name__)


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
    return result


async def _run_node(
    node: Node,
    emit,
    abort_event: Optional[asyncio.Event] = None,
    session: Optional[Session] = None,
) -> Any:
    t = node.type
    p = node.params or {}
    if t in ("start", "end"):
        return None
    if t == "navigate":
        return await actions.navigate(str(p["url"]))
    if t in ("click", "fill"):
        selector = str(p["selector"])
        value = "" if t == "click" else str(p.get("value", ""))
        try:
            return await _run_deterministic_action(t, selector, value)
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
                )
            except Exception:
                raise exc
    if t == "wait":
        return await _wait_cancellable(int(p["ms"]), abort_event)
    if t == "extract":
        return await actions.extract(str(p.get("instruction", "")))
    if t == "fuzzy_action":
        agent = FuzzyAgent()

        async def on_progress(msg: str) -> None:
            await emit("node_progress", node_id=node.id, message=msg)

        return await agent.run_fuzzy_action(
            instruction=str(p.get("instruction", "")), on_progress=on_progress
        )
    if t == "condition":
        expr = p.get("expr")
        try:
            result = bool(expr) if expr is None else bool(eval(str(expr), {"__builtins__": {}}, {}))
        except Exception:
            result = True
        return {"condition": result}
    raise ValueError(f"Unknown node type: {t}")


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


async def run_workflow(
    workflow: Workflow,
    on_event: EventSender,
    *,
    abort_event: Optional[asyncio.Event] = None,
    session: Optional[Session] = None,
    workflow_id: Optional[str] = None,
) -> None:
    emit = _make_emit(on_event)
    nodes_by_id = {n.id: n for n in workflow.nodes}
    edges_by_source: dict[str, list[Edge]] = {}
    for e in workflow.edges:
        edges_by_source.setdefault(e.source, []).append(e)

    await emit("run_started")

    current_id: str | None = workflow.start_id
    visited: set[str] = set()
    try:
        while current_id is not None:
            if abort_event is not None and abort_event.is_set():
                await emit("run_aborted")
                return
            if current_id in visited:
                await emit(
                    "run_failed",
                    error=f"cycle detected at node {current_id!r}",
                )
                return
            visited.add(current_id)

            node = nodes_by_id.get(current_id)
            if node is None:
                await emit(
                    "run_failed",
                    error=f"node {current_id!r} not found in workflow",
                )
                return

            await emit("node_started", node_id=node.id)

            if session is not None and node.params:
                try:
                    resolved_params = resolve_params(
                        node.params, session, workflow_id=workflow_id
                    )
                except CredentialResolutionError as exc:
                    await emit("node_failed", node_id=node.id, error=str(exc))
                    await emit("run_failed", error=f"node {node.id} failed: {exc}")
                    return
                node = node.model_copy(update={"params": resolved_params})

            try:
                result = await _run_node(
                    node, emit, abort_event=abort_event, session=session
                )
            except Exception as exc:
                await emit("node_failed", node_id=node.id, error=str(exc))
                await emit("run_failed", error=f"node {node.id} failed: {exc}")
                return
            await emit("node_completed", node_id=node.id, output=result)

            if abort_event is not None and abort_event.is_set():
                await emit("run_aborted")
                return

            if node.type == "end":
                break

            next_edge = _pick_next_edge(node, edges_by_source.get(node.id, []), result)
            current_id = next_edge.target if next_edge is not None else None

        await emit("run_completed")
    except Exception as exc:
        await emit("run_failed", error=str(exc))
