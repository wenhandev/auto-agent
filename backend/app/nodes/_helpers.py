"""Shared helpers for data-transform nodes."""
from __future__ import annotations

import re
from typing import Any

from app.nodes.result import Item, NodeResult
from app.services.expressions import ExpressionError, evaluate

_EXPR_RE = re.compile(r"^\{\{\s*=\s*(.+?)\s*\}\}$", re.DOTALL)
REMOVE_SENTINEL = "__remove__"


def build_namespace(
    item: Item,
    input_items: list[Item],
    context: dict[str, NodeResult],
) -> dict[str, Any]:
    return {
        "nodes": context,
        "item": item,
        "items": [it.json for it in input_items],
        "params": {},
    }


def eval_value(value: Any, namespace: dict[str, Any]) -> Any:
    """Evaluate a literal or ``{{= ... }}`` expression."""
    if isinstance(value, str):
        match = _EXPR_RE.match(value.strip())
        if match:
            return evaluate(match.group(1).strip(), namespace)
    return value


def eval_field(
    field: Any,
    item: Item,
    input_items: list[Item],
    context: dict[str, NodeResult],
) -> Any:
    """Resolve a sort/aggregate field path or expression."""
    if isinstance(field, str):
        match = _EXPR_RE.match(field.strip())
        if match:
            ns = build_namespace(item, input_items, context)
            return evaluate(match.group(1).strip(), ns)
        return item.json.get(field)
    return field


def wrap_item_error(exc: Exception, *, index: int, action: str) -> ExpressionError:
    msg = str(exc)
    if isinstance(exc, ExpressionError):
        return ExpressionError(f"{action} failed at item index {index}: {msg}")
    return ExpressionError(f"{action} failed at item index {index}: {msg}")
