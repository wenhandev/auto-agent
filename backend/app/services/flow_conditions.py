"""Safe evaluation for ``condition`` and ``switch`` flow-control nodes."""

from __future__ import annotations

import re
from typing import Any

from app.nodes._helpers import eval_value
from app.nodes.result import Item, NodeResult
from app.services.expressions import ExpressionError
from app.services.predicate import PredicateError, evaluate_predicate

_EXPR_RE = re.compile(r"^\{\{\s*=\s*(.+?)\s*\}\}$", re.DOTALL)


class FlowConditionError(ValueError):
    """Raised when branch expression or predicate evaluation fails."""


def build_flow_namespace(
    *,
    context: dict[str, NodeResult] | None = None,
    input_items: list[Item] | None = None,
    params_namespace: dict[str, Any] | None = None,
    trigger_namespace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    items = input_items or []
    ns: dict[str, Any] = {
        "params": params_namespace or {},
        "nodes": context or {},
        "item": (items[0].json if items else {}),
        "items": [it.json for it in items],
        "input_items": items,
    }
    if trigger_namespace is not None:
        ns["run"] = trigger_namespace.get("context") or {}
        ns["trigger"] = {
            k: v for k, v in trigger_namespace.items() if k != "context"
        }
    return ns


def _has_predicate(params: dict[str, Any]) -> bool:
    pred = params.get("predicate")
    return isinstance(pred, dict) and ("left" in pred or "op" in pred)


def _eval_expr_value(expr: Any, namespace: dict[str, Any]) -> Any:
    if isinstance(expr, str):
        stripped = expr.strip()
        if _EXPR_RE.match(stripped):
            return eval_value(stripped, namespace)
        return eval_value(f"{{{{= {stripped} }}}}", namespace)
    return expr


def evaluate_condition(params: dict[str, Any], *, namespace: dict[str, Any]) -> dict[str, Any]:
    """Return branch output dict including ``condition`` and ``result`` bools."""
    if _has_predicate(params):
        pred = params["predicate"]
        assert isinstance(pred, dict)
        try:
            left = eval_value(pred.get("left"), namespace)
            op = str(pred.get("op", "=="))
            right = (
                eval_value(pred.get("right"), namespace)
                if "right" in pred
                else pred.get("right")
            )
            result = evaluate_predicate(left, op, right)
        except (ExpressionError, PredicateError) as exc:
            raise FlowConditionError(str(exc)) from exc
        serialised = {"left": left, "op": op, "right": right}
        return {
            "condition": result,
            "result": result,
            "predicate": serialised,
        }

    expr = params.get("expr")
    if expr is None or expr == "":
        return {"condition": True, "result": True}

    if isinstance(expr, bool):
        return {"condition": expr, "result": expr, "expr": expr}

    try:
        value = _eval_expr_value(expr, namespace)
        result = bool(value)
    except ExpressionError as exc:
        raise FlowConditionError(str(exc)) from exc

    return {"condition": result, "result": result, "expr": expr}


def evaluate_switch_case(params: dict[str, Any], *, namespace: dict[str, Any]) -> str:
    expr = params.get("expr")
    if expr is None:
        return ""
    if isinstance(expr, bool):
        return "true" if expr else "false"
    if not isinstance(expr, str):
        return "" if expr is None else str(expr)
    if expr.strip() == "":
        return ""
    try:
        value = _eval_expr_value(expr, namespace)
    except ExpressionError as exc:
        raise FlowConditionError(str(exc)) from exc
    return "" if value is None else str(value)


__all__ = [
    "FlowConditionError",
    "build_flow_namespace",
    "evaluate_condition",
    "evaluate_switch_case",
]
