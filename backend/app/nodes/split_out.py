from __future__ import annotations

from typing import Any

from app.nodes.result import Item
from app.services.expressions import ExpressionError


async def run(
    params: dict[str, Any],
    *,
    input_items: list[Item],
    context: dict[str, Any],
) -> list[Item]:
    field = params.get("field")
    if not field:
        raise ExpressionError("split_out requires field")
    out_field = str(params.get("out_field") or field)
    include_other_fields = bool(params.get("include_other_fields", True))

    out: list[Item] = []
    for item in input_items:
        arr = item.json.get(str(field))
        if arr is None:
            continue
        if not isinstance(arr, list):
            raise ExpressionError(
                f"split_out: field {field!r} is not an array on item {item.json!r}"
            )
        for elem in arr:
            if include_other_fields:
                data = {k: v for k, v in item.json.items() if k != str(field)}
            else:
                data = {}
            if isinstance(elem, dict):
                data.update(elem)
            else:
                data[out_field] = elem
            out.append(Item(json=data, binary=dict(item.binary)))
    return out
