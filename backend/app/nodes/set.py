from __future__ import annotations

from typing import Any

from app.nodes._helpers import REMOVE_SENTINEL, build_namespace, eval_value
from app.nodes.result import Item, NodeResult


async def run(
    params: dict[str, Any],
    *,
    input_items: list[Item],
    context: dict[str, NodeResult],
) -> list[Item]:
    assignments = params.get("assignments") or []
    keep_only_set = bool(params.get("keep_only_set", False))
    fields_to_remove = params.get("fields_to_remove") or []
    include_binary = bool(params.get("include_binary", True))

    out: list[Item] = []
    for item in input_items:
        ns = build_namespace(item, input_items, context)
        data: dict[str, Any] = {} if keep_only_set else dict(item.json)

        for name in fields_to_remove:
            data.pop(name, None)

        for assignment in assignments:
            name = str(assignment["name"])
            value = eval_value(assignment.get("value"), ns)
            if value is None or value == REMOVE_SENTINEL:
                data.pop(name, None)
            else:
                data[name] = value

        binary = dict(item.binary) if include_binary else {}
        out.append(Item(json=data, binary=binary))
    return out
