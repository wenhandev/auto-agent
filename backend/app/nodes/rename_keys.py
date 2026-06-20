from __future__ import annotations

from typing import Any

from app.nodes._helpers import build_namespace
from app.nodes.result import Item
from app.services.expressions import ExpressionError


async def run(
    params: dict[str, Any],
    *,
    input_items: list[Item],
    context: dict[str, Any],
) -> list[Item]:
    pairs = params.get("pairs") or params.get("renames") or []
    error_on_collision = bool(params.get("error_on_collision", False))

    out: list[Item] = []
    for item in input_items:
        _ = build_namespace(item, input_items, context)
        data = dict(item.json)
        for pair in pairs:
            from_key = str(pair["from"])
            to_key = str(pair["to"])
            if from_key not in data:
                continue
            value = data.pop(from_key)
            if error_on_collision and to_key in data:
                raise ExpressionError(
                    f"rename_keys: collision on key {to_key!r}"
                )
            data[to_key] = value
        out.append(Item(json=data, binary=dict(item.binary)))
    return out
