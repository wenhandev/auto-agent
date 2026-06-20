from __future__ import annotations

from typing import Any

from app.nodes._helpers import build_namespace, eval_value, wrap_item_error
from app.nodes.result import Item
from app.services.expressions import ExpressionError


async def run(
    params: dict[str, Any],
    *,
    input_items: list[Item],
    context: dict[str, Any],
) -> list[Item]:
    predicate = params.get("predicate") or params.get("expr") or "{{= true }}"

    out: list[Item] = []
    for index, item in enumerate(input_items):
        ns = build_namespace(item, input_items, context)
        try:
            keep = bool(eval_value(predicate, ns))
        except ExpressionError as exc:
            raise wrap_item_error(exc, index=index, action="filter") from exc
        if keep:
            out.append(item)
    return out
